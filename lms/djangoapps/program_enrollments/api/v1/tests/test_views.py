""" Tests for the v1 program enrollment API Views """
from uuid import uuid4
from itertools import product
from openedx.core.lib.api.tests.mixins import JwtMixin
from openedx.core.djangoapps.catalog.tests.factories import (
    CourseFactory,
    CourseRunFactory,
    PathwayFactory,
    ProgramFactory,
    ProgramTypeFactory
)
from openedx.core.djangolib.testing.utils import CacheIsolationTestCase
from program_enrollments.api.v1.constants import CourseEnrollmentResponseStatuses as CourseStatuses
from program_enrollments.models import ProgramCourseEnrollment, ProgramEnrollment
from program_enrollments.tests.factories import ProgramEnrollmentFactory, ProgramCourseEnrollmentFactory

class RequestMixin(JwtMixin):
    """
    Mixin with authenticated get/post/put/patch/delete helper functions.

    Expects implementing classes to provide ``self.client`` attribute.
    """

    def get(self, path, user):
        """
        Perform a GET on the given path, optionally with a user.
        """
        return self._request('get', path, user)

    def post(self, path, data, user):
        """
        Perform a POST on the given path, optionally with a user.
        """
        return self._request('post', path, user, data)

    def put(self, path, data, user):
        """
        Perform a PUT on the given path, optionally with a user.
        """
        return self._request('put', path, user, data)

    def patch(self, path, data, user):
        """
        Perform a PATCH on the given path, optionally with a user.
        """
        return self._request('patch', path, user, data)

    def delete(self, path, user):
        """
        Perform a DELETE on the given, optionally with a user.
        """
        return self._request('delete', path, user)

    def _request(self, method, path, user, data=None):
        """
        Perform an HTTP request of the given method.

        If user is not None, include a JWT auth header.
        """
        kwargs = {'follow': True}
        if user:
            kwargs['HTTP_AUTHORIZATION'] = self.generate_jwt_header(
                user, admin=user.is_staff,
            )
        if data:
            kwargs['data'] = json.dumps(data)
            kwargs['content_type'] = 'application/json'
        if not (path.startswith('http://') or path.startswith('https://')):
            path = self.api_root + path
        return getattr(self.client, method.lower())(path, **kwargs)


class MockAPITestMixin(RequestMixin):
    """ Base mixin for tests for the v1 API. """
    api_root = '/api/v1/'
    path_suffix = None  # Define me in subclasses

    @property
    def path(self):
        return self.api_root + self.path_suffix

    def setUp(self):
        super().setUp()
        self.user = UserFactory()
        permissions = [
            'program_enrollments.add_programenrollment',
            'program_enrollments.change_programenrollment',
            'program_enrollments.delete_programenrollment',
            'program_enrollments.add_programcourseenrollment',
            'program_enrollments.change_programcourseenrollment',
            'program_enrollments.delete_programcourseenrollment',
        ]
        self.admin_program_enrollment_group = GroupFactory(
            name='admin_program_enrollment',
            permissions=permissions,
        )
        self.admin_user = UserFactory(groups=[self.admin_program_enrollment_group])


    def test_unauthenticated(self):
        response = self.get(self.path, None)
        self.assertEqual(response.status_code, 401)


class ProgramCacheTestCaseMixin(CacheIsolationMixin):
    """
    Mixin for using program cache in tests
    """
    ENABLED_CACHES = ['default']

    def setup_catalog_cache(self, program_uuid, organization_key):
        """
        helper function to initialize a cached program with an single authoring_organization
        """
        catalog_org = CatalogOrganizationFactory.create(key=organization_key)
        program = ProgramFactory.create(
            uuid=program_uuid,
            authoring_organizations=[catalog_org]
        )
        cache.set(PROGRAM_CACHE_KEY_TPL.format(uuid=program_uuid), program, None)
        return program


@ddt.ddt
class MockCourseEnrollmentPostTests(MockAPITestMixin, APITestCase, ProgramCacheTestCaseMixin):
    """ Tests for mock course enrollment """

    @classmethod
    def setUpClass(cls):
        super(CacheIsolationTestCase, cls).setUpClass()
        cls.start_cache_isolation()

    @classmethod
    def tearDownClass(cls):
        cls.end_cache_isolation()
        super(CacheIsolationTestCase, cls).tearDownClass()

    def setUp(self):
        super(MockCourseEnrollmentPostTests, self).setUp()
        self.clear_caches()
        self.addCleanup(self.clear_caches) 
        self.program_uuid = uuid4()
        self.organization_key = "orgkey"
        self.program = self.setup_catalog_cache(self.program_uuid, self.organization_key)        
        self.course = next(self.program.courses)
        self.course_run = next(self.course.course_runs)
        self.course_not_in_program = CourseFactory()
        self.path_suffix = self.build_path(self.program, self.course_run)
        
    def learner_enrollment(self, student_key, status="active"):
        return {"student_key": student_key, "status": status}
    
    def build_path(self, program, course):
        return 'programs/{}/courses/{}/enrollments'.format(program, course)

    def test_enrollments_empty_course(self):
        ProgramEnrollmentFactory.create(external_user_key='l1', program_uuid=self.program_uuid)
        ProgramEnrollmentFactory.create(external_user_key='l2', program_uuid=self.program_uuid)
        ProgramEnrollmentFactory.create(external_user_key='l3-waiting', program_uuid=self.program_uuid, user=None)
        ProgramEnrollmentFactory.create(external_user_key='l4-waiting', program_uuid=self.program_uuid, user=None)
        post_data = [
            self.learner_enrollment("l1", "active"),
            self.learner_enrollment("l2", "inactive"),
            self.learner_enrollment("l3-waiting", "active"),
            self.learner_enrollment("l4-waiting", "inactive"),
        ]
        response = self.post(self.path, post_data, self.admin_user)
        self.assertEqual(200, response.status_code)
        self.assertDictEqual(
            {
                "l1": "active",
                "l2": "inactive",
                "l3-waiting": "active",
                "l4-waiting": "inactive",
            },
            response.data
        )
        self.assert_program_course_enrollment("l1", True, True)
        self.assert_program_course_enrollment("l2", False, True)
        self.assert_program_course_enrollment("l3-waiting", True, False)
        self.assert_program_course_enrollment("l4-waiting", False, False)

    def test_duplicate(self):
        post_data = [
            self.learner_enrollment("l1", "active"),
            self.learner_enrollment("l1", "active"),
        ]
        response = self.post(self.path, post_data, self.admin_user)
        self.assertEqual(422, response.status_code)
        self.assertDictEqual(
            {
                "l1": CourseStatuses.DUPLICATED
            },
            response.data
        )

    def test_conflict(self):
        prog_enroll = ProgramEnrollmentFactory.create(external_user_key='l1', program_uuid=self.program_uuid)
        ProgramCourseEnrollmentFactory.create(program_enrollment=prog_enroll)
        post_data = [self.learner_enrollment("l1")]
        response = self.post(self.path, post_data, self.admin_user)
        self.assertEqual(422, response.status_code)
        self.assertDictEqual({'l1': CourseStatuses.CONFLICT}, response.data)

    def user_not_in_program(self):
        ProgramEnrollmentFactory.create(external_user_key='l1', program_uuid=self.program_uuid)
        post_data = [
            self.learner_enrollment("l1"),
            self.learner_enrollment("l2"),
        ]
        response = self.post(self.path, post_data, self.admin_user)
        self.assertEqual(207, response.status_code)
        self.assertDictEqual(
            {
                "l1": "active",
                "l2": "not-in-program",
            },
            response.data
        )

    def assert_program_course_enrollment(self, external_user_key, is_active, expected_course_enrollment):
        enrollment = ProgramCourseEnrollment.objects.get(program_enrollment__external_user_key=external_user_key)
        self.assertEqual(enrollment.status, "active" if is_active else "inactive")
        course_enrollment = enrollment.course_enrollment
        self.assertEqual(expected_course_enrollment, bool(enrollment.course_enrollment))
        if expected_course_enrollment:
            self.assertEqual(expected_course_enrollment.is_active, is_active)

    def test_207_multi_status(self):
        """ Also tests duplicates """
        post_data = [
            self.learner_enrollment("A", "active"),
            self.learner_enrollment("A", "inactive"),
            self.learner_enrollment("B", "not-a-status"),
            self.learner_enrollment("C", "active"),
        ]
        response = self.post(self.path, post_data, self.user)
        self.assertEqual(207, response.status_code)
        self.assertDictEqual(
            {
                'A': 'duplicated',
                'B': 'invalid-status',
                'C': 'active',
            },
            response.data
        )

    def test_403_forbidden(self):
        post_data = [self.learner_enrollment("A")]
        response = self.post(path_403, post_data, self.user)
        self.assertEqual(403, response.status_code)

    def test_413_payload_too_large(self):
        post_data = [self.learner_enrollment(str(i)) for i in range(30)]
        response = self.post(self.path, post_data, self.admin_user)
        self.assertEqual(413, response.status_code)

    def test_404_not_found_program(self):
        paths = [
            self.build_path("nonexistant-program", self.course_run),
            self.build_path(self.program, "nonexistant-course"),
            self.build_path(self.program, next(self.course_not_in_program.course_runs)),
        ]
        post_data = [self.learner_enrollment("A")]
        for path_404 in paths:
            response = self.post(path_404, post_data, self.user)
            self.assertEqual(404, response.status_code)

    def test_invalid_status(self):
        post_data = [self.learner_enrollment('A', 'this-is-not-a-status')]
        response = self.post(self.path, post_data, self.admin_user)
        self.assertEqual(422, response.status_code)
        self.assertDictEqual({'A': CourseStatuses.INVALID_STATUS}, response.data)

    @ddt.data(
        [{'status': 'active'}],
        [{'student_key': '000'}],
        ["this isn't even a dict!"],
        [{'student_key': '000', 'status': 'active'}, "bad_data"],
    )
    def test_422_unprocessable_entity_bad_data(self, post_data):
        response = self.post(self.path, post_data, self.admin_user)
        self.assertEqual(response.status_code, 422)
        self.assertIn('invalid enrollment record', response.data)
