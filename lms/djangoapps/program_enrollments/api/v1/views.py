# -*- coding: utf-8 -*-
"""
ProgramEnrollment Views
"""
from __future__ import unicode_literals

from collections import OrderedDict, Counter
from functools import wraps

from lms.djangoapps.program_enrollments.api.v1.serializers import ProgramEnrollmentSerializer
from lms.djangoapps.program_enrollments.models import ProgramEnrollment
from edx_rest_framework_extensions import permissions
from edx_rest_framework_extensions.auth.jwt.authentication import JwtAuthentication
from edx_rest_framework_extensions.auth.session.authentication import SessionAuthenticationAllowInactiveUser
from rest_framework import status
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response

from lms.djangoapps.program_enrollments.api.v1.serializers import ProgramEnrollmentListSerializer
from lms.djangoapps.program_enrollments.models import ProgramEnrollment
from openedx.core.djangoapps.catalog.utils import get_programs
from openedx.core.lib.api.authentication import OAuth2AuthenticationAllowInactiveUser
from openedx.core.lib.api.view_utils import DeveloperErrorViewMixin, PaginatedAPIView


def verify_program_exists(view_func):
    """
    Raises:
        An API error if the `program_key` kwarg in the wrapped function
        does not exist in the catalog programs cache.
    """
    @wraps(view_func)
    def wrapped_function(self, request, **kwargs):
        """
        Wraps the given view_function.
        """
        program_uuid = kwargs['program_key']
        program = get_programs(uuid=program_uuid)
        if not program:
            raise self.api_error(
                status_code=status.HTTP_404_NOT_FOUND,
                developer_message='no program exists with given key',
                error_code='program_does_not_exist'
            )
        return view_func(self, request, **kwargs)
    return wrapped_function


class ProgramEnrollmentPagination(CursorPagination):
    """
    Pagination class for Program Enrollments.
    """
    ordering = 'id'
    page_size = 100
    page_size_query_param = 'page_size'

    def get_page_size(self, request):
        """
        Get the page size based on the defined page size parameter if defined.
        """
        try:
            page_size_string = request.query_params[self.page_size_query_param]
            return int(page_size_string)
        except (KeyError, ValueError):
            pass

        return self.page_size


class ProgramEnrollmentsView(DeveloperErrorViewMixin, PaginatedAPIView):
    """
    A view for Create/Read/Update methods on Program Enrollment data.

    Path: `/api/program_enrollments/v1/programs/{program_key}/enrollments/`
    The path can contain an optional `page_size?=N` query parameter.  The default page size is 100.

    Returns:
      * 200: OK - Contains a paginated set of program enrollment data.
      * 401: The requesting user is not authenticated.
      * 403: The requesting user lacks access for the given program.
      * 404: The requested program does not exist.

    Response:
    In the case of a 200 response code, the response will include a paginated
    data set.  The `results` section of the response consists of a list of
    program enrollment records, where each record contains the following keys:
      * student_key: The identifier of the student enrolled in the program.
      * status: The student's enrollment status.
      * account_exists: A boolean indicating if the student has created an edx-platform user account.
      * curriculum_uuid: The curriculum UUID of the enrollment record for the (student, program).

    Example:
    {
        "next": null,
        "previous": "http://testserver.com/api/program_enrollments/v1/programs/{program_key}/enrollments/?curor=abcd",
        "results": [
            {
                "student_key": "user-0", "status": "pending",
                "account_exists": False, "curriculum_uuid": "00000000-1111-2222-3333-444444444444"
            },
            {
                "student_key": "user-1", "status": "pending",
                "account_exists": False, "curriculum_uuid": "00000001-1111-2222-3333-444444444444"
            },
            {
                "student_key": "user-2", "status": "enrolled",
                "account_exists": True, "curriculum_uuid": "00000002-1111-2222-3333-444444444444"
            },
            {
                "student_key": "user-3", "status": "enrolled",
                "account_exists": True, "curriculum_uuid": "00000003-1111-2222-3333-444444444444"
            },
        ],
    }

    """
    authentication_classes = (
        JwtAuthentication,
        OAuth2AuthenticationAllowInactiveUser,
        SessionAuthenticationAllowInactiveUser,
    )
    permission_classes = (permissions.JWT_RESTRICTED_APPLICATION_OR_USER_ACCESS,)
    pagination_class = ProgramEnrollmentPagination

    @verify_program_exists
    def get(self, request, program_key=None):
        enrollments = ProgramEnrollment.objects.filter(program_uuid=program_key)
        paginated_enrollments = self.paginate_queryset(enrollments)
        serializer = ProgramEnrollmentListSerializer(paginated_enrollments, many=True)
        return self.get_paginated_response(serializer.data)

    @verify_program_exists
    def post(self, request, *args, **kwargs):
        ERROR_CONFLICT = 'conflict'
        ERROR_DUPLICATED = 'duplicated'
        ERROR_INVALID_STATUS = 'invalid-status'
        if len(request.data) > 25:
            return Response(
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content_type='application/json',
            )

        program_uuid = kwargs['program_key']
        student_data = OrderedDict((
            row['external_user_key'],
            {
                'program_uuid': program_uuid,
                'curriculum_uuid': row.get('curriculum_uuid'),
                'status': row.get('status'),
                'external_user_key': row.get('external_user_key'),
            })
            for row in request.data
        )

        total_student_keys = [enrollment.get('external_user_key') for enrollment in request.data]
        key_counter = Counter(total_student_keys)

        response_data = {}
        for student_key, count in key_counter.items():
            if count > 1:
                response_data[student_key] = self.ERROR_DUPLICATED
                student_data.pop(student_key)

        existing_enrollments = ProgramEnrollment.bulk_read_by_student_key(program_uuid, student_data)
        for enrollment in existing_enrollments:
            response_data[enrollment.external_user_key] = self.ERROR_CONFLICT
            student_data.pop(enrollment.external_user_key)

        enrollments_to_create = {}

        for student_key, data in student_data.items():
            curriculum_uuid = data['curriculum_uuid']
            serializer = ProgramEnrollmentSerializer(data=data)

            if serializer.is_valid():
                enrollments_to_create[(student_key, curriculum_uuid)] = serializer
                response_data[student_key] = data.get('status')
            else:
                if ('status' in serializer.errors and serializer.errors['status'][0].code == 'invalid_choice'):
                    response_data[student_key] = self.ERROR_INVALID_STATUS
                else:
                    return Response(
                        'invalid enrollment record',
                        HTTP_422_UNPROCESSABLE_ENTITY
                    )

        for enrollment_serializer in enrollments_to_create.values():
            # create the model
            enrollment_serializer.save()
            # TODO: make this a bulk save

        if not enrollments_to_create:
            return Response(
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                data=response_data,
                content_type='application/json',
            )

        if len(request.data) != len(enrollments_to_create):
            return Response(
                status=status.HTTP_207_MULTI_STATUS,
                data=response_data,
                content_type='application/json',
            )

        return Response(
            status=status.HTTP_201_CREATED,
            data=response_data,
            content_type='application/json',
        )
