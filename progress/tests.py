# pylint: disable=E1101
"""
Run these tests @ Devstack:
    paver test_system -s lms --test_id=lms/djangoapps/progress/tests.py
"""
import uuid
from mock import MagicMock, patch
from datetime import datetime
from django.utils.timezone import UTC

from django.test.utils import override_settings
from django.conf import settings

from capa.tests.response_xml_factory import StringResponseXMLFactory

from student.tests.factories import UserFactory, AdminFactory
from courseware.tests.factories import StaffFactory
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase, mixed_store_config
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory
from progress.models import CourseModuleCompletion, StudentProgress, StudentProgressHistory
from courseware.model_data import FieldDataCache
from courseware import module_render
from util.signals import course_deleted
from gradebook.test_utils import SignalDisconnectTestMixin


MODULESTORE_CONFIG = mixed_store_config(settings.COMMON_TEST_DATA_ROOT, {})


@override_settings(MODULESTORE=MODULESTORE_CONFIG)
@override_settings(STUDENT_GRADEBOOK=True)
class CourseModuleCompletionTests(SignalDisconnectTestMixin, ModuleStoreTestCase):
    """ Test suite for CourseModuleCompletion """

    def get_module_for_user(self, user, course, problem):
        """Helper function to get useful module at self.location in self.course_id for user"""
        mock_request = MagicMock()
        mock_request.user = user
        field_data_cache = FieldDataCache.cache_for_descriptor_descendents(
            course.id, user, course, depth=2)

        return module_render.get_module(  # pylint: disable=protected-access
            user,
            mock_request,
            problem.location,
            field_data_cache,
        )

    def setUp(self):
        super(CourseModuleCompletionTests, self).setUp()
        self.user = UserFactory()
        self._create_course()

    def _create_course(self, start=None, end=None):
        """
        Creates a course to run tests against
        """
        self.course = CourseFactory.create(
            start=start,
            end=end
        )
        self.course.always_recalculate_grades = True
        test_data = '<html>{}</html>'.format(str(uuid.uuid4()))
        self.chapter1 = ItemFactory.create(
            category="chapter",
            parent_location=self.course.location,
            data=test_data,
            display_name="Chapter 1"
        )
        chapter2 = ItemFactory.create(
            category="chapter",
            parent_location=self.course.location,
            data=test_data,
            display_name="Chapter 2"
        )
        sub_section = ItemFactory.create(
            category="sequential",
            parent_location=self.chapter1.location,
            data=test_data,
            display_name="Sequence 1",
        )
        sub_section2 = ItemFactory.create(
            category="sequential",
            parent_location=chapter2.location,
            data=test_data,
            display_name="Sequence 2",
        )
        self.vertical = ItemFactory.create(
            parent_location=sub_section.location,
            category="vertical",
            metadata={'graded': True, 'format': 'Homework'},
            display_name=u"test vertical",
        )
        vertical2 = ItemFactory.create(
            parent_location=sub_section2.location,
            category="vertical",
            metadata={'graded': True, 'format': 'Lab'},
            display_name=u"test vertical 2",
        )
        vertical3 = ItemFactory.create(
            parent_location=sub_section2.location,
            category="vertical",
            metadata={'graded': True, 'format': 'Lab'},
            display_name=u"Discussion Course",
        )
        ItemFactory.create(
            parent_location=vertical2.location,
            category='problem',
            data=StringResponseXMLFactory().build_xml(answer='foo'),
            metadata={'rerandomize': 'always'},
            display_name="test problem 1",
            max_grade=45
        )
        self.problem = ItemFactory.create(
            parent_location=self.vertical.location,
            category='problem',
            data=StringResponseXMLFactory().build_xml(answer='bar'),
            display_name="homework problem 1",
            metadata={'rerandomize': 'always', 'graded': True, 'format': "Homework"}
        )
        self.problem2 = ItemFactory.create(
            parent_location=vertical2.location,
            category='problem',
            data=StringResponseXMLFactory().build_xml(answer='bar'),
            display_name="homework problem 2",
            metadata={'rerandomize': 'always', 'graded': True, 'format': "Homework"}
        )
        self.problem3 = ItemFactory.create(
            parent_location=vertical2.location,
            category='problem',
            data=StringResponseXMLFactory().build_xml(answer='bar'),
            display_name="lab problem 1",
            metadata={'rerandomize': 'always', 'graded': True, 'format': "Lab"}
        )
        self.problem4 = ItemFactory.create(
            parent_location=vertical2.location,
            category='problem',
            data=StringResponseXMLFactory().build_xml(answer='bar'),
            display_name="midterm problem 2",
            metadata={'rerandomize': 'always', 'graded': True, 'format': "Midterm Exam"}
        )
        self.problem5 = ItemFactory.create(
            parent_location=vertical2.location,
            category='problem',
            data=StringResponseXMLFactory().build_xml(answer='bar'),
            display_name="final problem 2",
            metadata={'rerandomize': 'always', 'graded': True, 'format': "Final Exam"}
        )
        self.problem6 = ItemFactory.create(
            parent_location=vertical3.location,
            category='problem',
            data=StringResponseXMLFactory().build_xml(answer='bar'),
            display_name="Problem 6",
        )
        ItemFactory.create(
            parent_location=vertical3.location,
            category='discussion-course',
            display_name="Course Discussion Item",
        )

    def test_save_completion(self):
        """
        Save a CourseModuleCompletion and fetch it again
        """
        module = self.get_module_for_user(self.user, self.course, self.problem4)
        module.system.publish(module, 'progress', {})

        completion_fetch = CourseModuleCompletion.objects.get(
            user=self.user.id,
            course_id=self.course.id,
            content_id=self.problem4.location
        )
        self.assertIsNotNone(completion_fetch)

    @patch.dict(settings.FEATURES, {'ALLOW_STUDENT_STATE_UPDATES_ON_CLOSED_COURSE': False})
    def test_save_completion_with_feature_flag(self):
        """
        Save a CourseModuleCompletion with the feature flag, but the course is still open
        """
        module = self.get_module_for_user(self.user, self.course, self.problem4)
        module.system.publish(module, 'progress', {})

        completion_fetch = CourseModuleCompletion.objects.get(
            user=self.user.id,
            course_id=self.course.id,
            content_id=self.problem4.location
        )
        self.assertIsNotNone(completion_fetch)

    @patch.dict(settings.FEATURES, {'ALLOW_STUDENT_STATE_UPDATES_ON_CLOSED_COURSE': False})
    def test_save_completion_admin_not_started(self):
        """
        Save a CourseModuleCompletion with the feature flag on a course that has not yet started
        but Admins should be able to write
        """
        self._create_course(start=datetime(3000, 1, 1, tzinfo=UTC()))

        self.user = AdminFactory()

        module = self.get_module_for_user(self.user, self.course, self.problem4)
        module.system.publish(module, 'progress', {})

        completion_fetch = CourseModuleCompletion.objects.get(
            user=self.user.id,
            course_id=self.course.id,
            content_id=self.problem4.location
        )
        self.assertIsNotNone(completion_fetch)

    @patch.dict(settings.FEATURES, {'ALLOW_STUDENT_STATE_UPDATES_ON_CLOSED_COURSE': False})
    def test_save_completion_staff_not_started(self):
        """
        Save a CourseModuleCompletion with the feature flag on a course that has not yet started
        but Staff should be able to write
        """
        self._create_course(start=datetime(3000, 1, 1, tzinfo=UTC()))

        self.user = StaffFactory(course_key=self.course.id)

        module = self.get_module_for_user(self.user, self.course, self.problem4)
        module.system.publish(module, 'progress', {})

        completion_fetch = CourseModuleCompletion.objects.get(
            user=self.user.id,
            course_id=self.course.id,
            content_id=self.problem4.location
        )
        self.assertIsNotNone(completion_fetch)

    @patch.dict(settings.FEATURES, {'ALLOW_STUDENT_STATE_UPDATES_ON_CLOSED_COURSE': False})
    def test_save_completion_admin_ended(self):
        """
        Save a CourseModuleCompletion with the feature flag on a course that has not yet started
        but Admins should be able to write
        """
        self._create_course(end=datetime(1999, 1, 1, tzinfo=UTC()))

        self.user = AdminFactory()

        module = self.get_module_for_user(self.user, self.course, self.problem4)
        module.system.publish(module, 'progress', {})

        with self.assertRaises(CourseModuleCompletion.DoesNotExist):
            CourseModuleCompletion.objects.get(
                user=self.user.id,
                course_id=self.course.id,
                content_id=self.problem4.location
            )

    @patch.dict(settings.FEATURES, {'ALLOW_STUDENT_STATE_UPDATES_ON_CLOSED_COURSE': False})
    def test_save_completion_staff_ended(self):
        """
        Save a CourseModuleCompletion with the feature flag on a course that has not yet started
        but Staff should be able to write
        """
        self._create_course(end=datetime(1999, 1, 1, tzinfo=UTC()))

        self.user = StaffFactory(course_key=self.course.id)

        module = self.get_module_for_user(self.user, self.course, self.problem4)
        module.system.publish(module, 'progress', {})

        with self.assertRaises(CourseModuleCompletion.DoesNotExist):
            CourseModuleCompletion.objects.get(
                user=self.user.id,
                course_id=self.course.id,
                content_id=self.problem4.location
            )

    @patch.dict(settings.FEATURES, {'ALLOW_STUDENT_STATE_UPDATES_ON_CLOSED_COURSE': False})
    def test_save_completion_with_course_not_started(self):
        """
        Save a CourseModuleCompletion with the feature flag, but the course has not yet started
        """
        self._create_course(start=datetime(3000, 1, 1, tzinfo=UTC()))

        module = self.get_module_for_user(self.user, self.course, self.problem4)
        module.system.publish(module, 'progress', {})

        entry = CourseModuleCompletion.objects.get(
            user=self.user.id,
            course_id=self.course.id,
            content_id=self.problem4.location
        )
        self.assertIsNotNone(entry)

    @patch.dict(settings.FEATURES, {'ALLOW_STUDENT_STATE_UPDATES_ON_CLOSED_COURSE': False})
    def test_save_completion_with_course_already_ended(self):
        """
        Save a CourseModuleCompletion with the feature flag, but the course has already ended
        """
        self._create_course(
            start=datetime.now(UTC()),
            end=datetime(2000, 1, 1, tzinfo=UTC())
        )

        module = self.get_module_for_user(self.user, self.course, self.problem4)
        module.system.publish(module, 'progress', {})

        with self.assertRaises(CourseModuleCompletion.DoesNotExist):
            CourseModuleCompletion.objects.get(
                user=self.user.id,
                course_id=self.course.id,
                content_id=self.problem4.location
            )

    def test_progress_calc_on_invalid_module(self):
        """
        Tests progress calculations for invalid modules.
        We want to calculate progress of those module which are
        direct children of verticals. Modules at any other level
        of course tree should not be counted in progress.
        """
        self._create_course()
        # create a module whose parent is not a vertical
        module = ItemFactory.create(
            parent_location=self.chapter1.location,
            category='video',
            data={'data': '<video display_name="Test Video" />'}
        )
        module = self.get_module_for_user(self.user, self.course, module)
        module.system.publish(module, 'progress', {})

        progress = StudentProgress.objects.all()
        # assert there is no progress entry for a module whose parent is not a vertical
        self.assertEqual(len(progress), 0)

    @override_settings(PROGRESS_DETACHED_CATEGORIES=["group-project"])
    def test_progress_calc_on_detached_module(self):
        """
        Tests progress calculations for modules having detached categories
        """
        self._create_course()
        # create a module whose category is one of detached categories
        module = ItemFactory.create(
            parent_location=self.vertical.location,
            category='group-project',
        )
        module = self.get_module_for_user(self.user, self.course, module)
        module.system.publish(module, 'progress', {})

        progress = StudentProgress.objects.all()
        # assert there is no progress entry for a module whose category is in detached categories
        self.assertEqual(len(progress), 0)

    @override_settings(
        PROGRESS_DETACHED_CATEGORIES=["group-project"],
        PROGRESS_DETACHED_VERTICAL_CATEGORIES=["discussion-course"],
    )
    def test_progress_calc_on_vertical_with_detached_module(self):
        """
        Tests progress calculations for modules inside a vertical with detached categories
        """
        self._create_course()
        module = self.get_module_for_user(self.user, self.course, self.problem6)
        module.system.publish(module, 'progress', {})

        progress = StudentProgress.objects.all()
        # assert there is no progress entry for a module whose category is in detached categories
        self.assertEqual(len(progress), 0)

    def test_receiver_on_course_deleted(self):
        self._create_course(start=datetime(2010, 1, 1, tzinfo=UTC()), end=datetime(2020, 1, 1, tzinfo=UTC()))
        module = self.get_module_for_user(self.user, self.course, self.problem)
        module.system.publish(module, 'progress', {})

        progress = StudentProgress.objects.all()
        self.assertEqual(len(progress), 1)

        history = StudentProgressHistory.objects.all()
        self.assertEqual(len(history), 1)

        course_deleted.send(sender=None, course_key=self.course.id)

        progress = StudentProgress.objects.all()
        self.assertEqual(len(progress), 0)

        history = StudentProgressHistory.objects.all()
        self.assertEqual(len(history), 0)
