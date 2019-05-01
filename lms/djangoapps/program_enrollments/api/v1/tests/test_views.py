"""
Unit tests for ProgramEnrollment views.
"""
from __future__ import unicode_literals

import mock
import json

from uuid import uuid4

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from six import text_type

from lms.djangoapps.courseware.tests.factories import GlobalStaffFactory
from lms.djangoapps.program_enrollments.models import ProgramEnrollment
from student.tests.factories import UserFactory

from .factories import ProgramEnrollmentFactory


class ProgramEnrollmentListTest(APITestCase):
    """
    Tests for GET calls to the Program Enrollments API.
    """
    @classmethod
    def setUpClass(cls):
        super(ProgramEnrollmentListTest, cls).setUpClass()
        cls.program_uuid = '00000000-1111-2222-3333-444444444444'
        cls.curriculum_uuid = 'aaaaaaaa-1111-2222-3333-444444444444'
        cls.password = 'password'
        cls.student = UserFactory.create(username='student', password=cls.password)
        cls.global_staff = GlobalStaffFactory.create(username='global-staff', password=cls.password)

    @classmethod
    def tearDownClass(cls):
        super(ProgramEnrollmentListTest, cls).tearDownClass()

    def create_enrollments(self):
        """
        Helper method for creating program enrollment records.
        """
        for i in xrange(2):
            user_key = 'user-{}'.format(i)
            ProgramEnrollmentFactory.create(
                program_uuid=self.program_uuid,
                curriculum_uuid=self.curriculum_uuid,
                user=None,
                status='pending',
                external_user_key=user_key,
            )

        for i in xrange(2, 4):
            user_key = 'user-{}'.format(i)
            ProgramEnrollmentFactory.create(
                program_uuid=self.program_uuid, curriculum_uuid=self.curriculum_uuid, external_user_key=user_key,
            )

        self.addCleanup(self.destroy_enrollments)

    def destroy_enrollments(self):
        """
        Deletes program enrollments associated with this test case's program_uuid.
        """
        ProgramEnrollment.objects.filter(program_uuid=self.program_uuid).delete()

    def get_url(self, program_key=None):
        return reverse('programs_api:v1:program_enrollments', kwargs={'program_key': program_key})

    @mock.patch('lms.djangoapps.program_enrollments.api.v1.views.get_programs', autospec=True, return_value=None)
    def test_404_if_no_program_with_key(self, mock_get_programs):
        self.client.login(username=self.global_staff.username, password=self.password)
        response = self.client.get(self.get_url(self.program_uuid))
        assert status.HTTP_404_NOT_FOUND == response.status_code
        mock_get_programs.assert_called_once_with(uuid=self.program_uuid)

    def test_403_if_not_staff(self):
        self.client.login(username=self.student.username, password=self.password)
        response = self.client.get(self.get_url(self.program_uuid))
        assert status.HTTP_403_FORBIDDEN == response.status_code

    def test_401_if_anonymous(self):
        response = self.client.get(self.get_url(self.program_uuid))
        assert status.HTTP_401_UNAUTHORIZED == response.status_code

    def test_200_empty_results(self):
        self.client.login(username=self.global_staff.username, password=self.password)

        with mock.patch('lms.djangoapps.program_enrollments.api.v1.views.get_programs', autospec=True):
            response = self.client.get(self.get_url(self.program_uuid))

        assert status.HTTP_200_OK == response.status_code
        expected = {
            'next': None,
            'previous': None,
            'results': [],
        }
        assert expected == response.data

    def test_200_many_results(self):
        self.client.login(username=self.global_staff.username, password=self.password)

        self.create_enrollments()
        with mock.patch('lms.djangoapps.program_enrollments.api.v1.views.get_programs', autospec=True):
            response = self.client.get(self.get_url(self.program_uuid))

        assert status.HTTP_200_OK == response.status_code
        expected = {
            'next': None,
            'previous': None,
            'results': [
                {
                    'student_key': 'user-0', 'status': 'pending', 'account_exists': False,
                    'curriculum_uuid': text_type(self.curriculum_uuid),
                },
                {
                    'student_key': 'user-1', 'status': 'pending', 'account_exists': False,
                    'curriculum_uuid': text_type(self.curriculum_uuid),
                },
                {
                    'student_key': 'user-2', 'status': 'enrolled', 'account_exists': True,
                    'curriculum_uuid': text_type(self.curriculum_uuid),
                },
                {
                    'student_key': 'user-3', 'status': 'enrolled', 'account_exists': True,
                    'curriculum_uuid': text_type(self.curriculum_uuid),
                },
            ],
        }
        assert expected == response.data

    def test_200_many_pages(self):
        self.client.login(username=self.global_staff.username, password=self.password)

        self.create_enrollments()
        with mock.patch('lms.djangoapps.program_enrollments.api.v1.views.get_programs', autospec=True):
            url = self.get_url(self.program_uuid) + '?page_size=2'
            response = self.client.get(url)

            assert status.HTTP_200_OK == response.status_code
            expected_results = [
                {
                    'student_key': 'user-0', 'status': 'pending', 'account_exists': False,
                    'curriculum_uuid': text_type(self.curriculum_uuid),
                },
                {
                    'student_key': 'user-1', 'status': 'pending', 'account_exists': False,
                    'curriculum_uuid': text_type(self.curriculum_uuid),
                },
            ]
            assert expected_results == response.data['results']
            # there's going to be a 'cursor' query param, but we have no way of knowing it's value
            assert response.data['next'] is not None
            assert self.get_url(self.program_uuid) in response.data['next']
            assert '?cursor=' in response.data['next']
            assert response.data['previous'] is None

            next_response = self.client.get(response.data['next'])
            assert status.HTTP_200_OK == next_response.status_code
            next_expected_results = [
                {
                    'student_key': 'user-2', 'status': 'enrolled', 'account_exists': True,
                    'curriculum_uuid': text_type(self.curriculum_uuid),
                },
                {
                    'student_key': 'user-3', 'status': 'enrolled', 'account_exists': True,
                    'curriculum_uuid': text_type(self.curriculum_uuid),
                },
            ]
            assert next_expected_results == next_response.data['results']
            assert next_response.data['next'] is None
            # there's going to be a 'cursor' query param, but we have no way of knowing it's value
            assert next_response.data['previous'] is not None
            assert self.get_url(self.program_uuid) in next_response.data['previous']
            assert '?cursor=' in next_response.data['previous']


class ProgramEnrollmentViewTests(APITestCase):
    """
    Tests for the ProgramEnrollment view.
    """

    def test_successfully_post_enrollments(self):
        program_key = uuid4()
        statuses = ['pending', 'enrolled', 'pending']
        external_user_keys = ['abc1', 'efg2', 'hij3']

        curriculum_uuid = uuid4()
        curriculum_uuids = [curriculum_uuid, curriculum_uuid, uuid4()]
        post_data = [
            {
                'external_user_key': e,
                'status': s,
                'curriculum_uuid': str(c)
            } 
            for e, s, c in zip(external_user_keys, statuses, curriculum_uuids)
        ]

        self.url = reverse('programs_api:v1:program_enrollments', args=[program_key])

        response = self.client.post(self.url, json.dumps(post_data), content_type='application/json')
        self.assertEqual(response.status_code, 201)

        for i in range(3):
            enrollment = ProgramEnrollment.objects.filter(external_user_key=external_user_keys[i])[0]
            actual_external_user_key = enrollment.external_user_key
            self.assertEqual(actual_external_user_key, external_user_keys[i])

            actual_program_uuid = enrollment.program_uuid
            actual_status = enrollment.status
            actual_curriculum_uuid = enrollment.curriculum_uuid
            
            self.assertEqual(actual_program_uuid, program_key)
            self.assertEqual(actual_status, statuses[i])
            self.assertEqual(actual_curriculum_uuid, curriculum_uuids[i])
    
    def test_enrollment_payload_limit(self):
        def student_enrollment(status):
            return {
                'status': status,
                'external_user_key': str(uuid4().hex[0:10]),
                'curriculum_uuid': str(uuid4())
            }
        post_data = []
        for i in range(26):
            post_data += student_enrollment('enrolled')

        self.url = reverse('programs_api:v1:program_enrollments', args=[uuid4()])
        response = self.client.post(self.url, json.dumps(post_data), content_type='application/json')
        self.assertEqual(response.status_code, 413)
    
    def test_duplicate_enrollment(self):
        def student_enrollment(status, external_user_key):
            return {
                'status': status,
                'external_user_key': external_user_key or str(uuid4().hex[0:10]),
                'curriculum_uuid': str(uuid4())
            }
        post_data = [
            student_enrollment('enrolled', '001'),
            student_enrollment('enrolled', '002'),
            student_enrollment('enrolled', '001'),
        ]
        
        self.url = reverse('programs_api:v1:program_enrollments', args=[uuid4()])
        response = self.client.post(self.url, json.dumps(post_data), content_type='application/json')

        self.assertEqual(response.status_code, 207)
        self.assertEqual(response.data, {
            '001': 'duplicated',
            '002': 'enrolled',
        })

    def test_unprocessable_enrollment(self):
        self.url = reverse('programs_api:v1:program_enrollments', args=[uuid4()])
        response = self.client.post(
            self.url,
            [{'status': 'enrolled'}],
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 422)

