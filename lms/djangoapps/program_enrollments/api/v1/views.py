# -*- coding: utf-8 -*-
"""
ProgramEnrollment Views
"""
from __future__ import unicode_literals

from django.http import HttpResponse
from course_modes.models import CourseMode
from student.models import CourseEnrollment
from edx_rest_framework_extensions.auth.jwt.authentication import JwtAuthentication
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import (
    HTTP_202_ACCEPTED,
    HTTP_207_MULTI_STATUS,
    HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    HTTP_422_UNPROCESSABLE_ENTITY,
)

from openedx.core.djangoapps.catalog.utils import get_programs
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview


from program_enrollments.api.v1.constants import CourseEnrollmentResponseStatuses
from program_enrollments.models import ProgramEnrollment, ProgramCourseEnrollment
from program_enrollments.serializers import ProgramCourseEnrollmentRequestSerializer
from program_enrollments.utils import get_user_by_organization, ProviderDoesNotExistException


class ProgramEnrollmentsView(APIView):
    """
    POST view for ProgramEnrollments
    """

    def get(self, request, *args, **kwargs):
        return HttpResponse('result')


class ProgramSpecificViewMixin(object):
    """
    A mixin for views that operate on or within a specific program.
    """

    @property
    def program(self):       
        """
        The program specified by the `program_key` URL parameter.
        """
        if self._program is None:
            program = get_programs(self.kwargs['program_key'])
            if program is None:
                raise Http404()
            self._program = program
        return self._program


class ProgramCourseSpecificViewMixin(ProgramSpecificViewMixin):
    """
    A mixin for views that operate on or within a specific course in a program
    """

    def check_existance_and_membership(self):
        """ 
        Attempting to look up the course and program will trigger 404 responses if:
        - The program does not exist
        - The course run (course_key) does not exist
        - The course run is not part of the program
        """
        self.course  # pylint: disable=pointless-statement

    @property
    def course(self):
        """
        The course specified by the `course_id` URL parameter.
        """
        if self._course is None:
            try:
                course = CourseOverview.get_from_id(self.kwargs['course_id'])
            except CourseOverview.DoesNotExist:
                raise Http404()
            if course not in self.program["courses"]:
                raise Http404()
            self._course = course
        return self._course


class ProgramCourseEnrollmentsView(APIView, ProgramCourseSpecificViewMixin):
    """
    A view for enrolling students in a course through a program, 
    modifying program course enrollments, and listing program course 
    enrollments

    Path: /api/v1/programs/{program_key}/courses/{course_id}/enrollments

    Accepts: [POST]

    ------------------------------------------------------------------------------------
    POST 
    ------------------------------------------------------------------------------------

    Returns:
     * 200: Returns a map of students and their enrollment status.
     * 207: Not all students enrolled. Returns resulting enrollment status.
     * 401: User is not authenticated
     * 403: User lacks read access organization of specified program.
     * 404: Program does not exist, or course does not exist in program
     * 422: Invalid request, unable to enroll students.
    """
    authentication_classes = (JwtAuthentication, SessionAuthentication)
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        """
        Enroll a list of students in a course in a program
        """
        self.check_existance_and_membership()
        results = {}
        seen_student_keys = set()
        enrollments = []

        if not isinstance(request.data, list):
            raise ValidationError()

        if len(request.data) > 25:
            return Response(
                'enrollment limit 25', HTTP_413_REQUEST_ENTITY_TOO_LARGE
            )
        try:
            for enrollment_request in request.data:
                error_status = self.check_enrollment_request(enrollment, seen_student_keys)
                if error_status:
                    results[enrollment_request["student_key"]] = error_status
                else:
                    enrollments.append(enrollment_request)
        except KeyError:
            return Response('student key required', HTTP_422_UNPROCESSABLE_ENTITY) 
        except ValidationError:
            return Response('invalid enrollment record', HTTP_422_UNPROCESSABLE_ENTITY)
                
        program_enrollments = self.get_existing_program_enrollments(enrollments)
        for enrollment in enrollments:
            results[enrollment["student_key"]] = self.enroll_learner_in_course(enrollment, program_enrollments)
        
        good_enrolled_students = sum([1 for k, v in results.items() if v not in ResponseStatuses.ERROR_STATUSES])
        if not good_enrolled_students:
            return Response(results, HTTP_422_UNPROCESSABLE_ENTITY)
        if good_enrolled_students != len(results):
            return Response(results, HTTP_207_MULTI_STATUS)
        else:
            return Response(results)
    
    def check_enrollment_request(self, enrollment, seen_student_keys):
        """
        Checks that the given enrollment record is valid and hasn't been duplicated
        """
        student_key = enrollment['student_key']
        if student_key in seen_student_keys:
            return CourseEnrollmentResponseStatuses.DUPLICATED
        enrollment_serializer = ProgramCourseEnrollmentRequestSerializer(enrollment)
        try:
            enrollment_serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            if enrollment_serializer.has_invalid_status():
                return CourseEnrollmentResponseStatuses.INVALID_STATUS
            else:
                raise e

    def enroll_learner_in_course(self, enrollment_request, program_enrollments):
        """
        Attempts to enroll the specified user into the course as a part of the
         given program enrollment with the given status

        Returns the actual status
        """
        student_key = enrollment_request['student_key']
        try:
            program_enrollment = program_enrollments[student_key]
        except KeyError:
            return CourseEnrollmentResponseStatuses.NOT_IN_PROGRAM
        if program_enrollment.get_program_course_enrollment(self.course):
            return CourseEnrollmentResponseStatuses.CONFLICT                    

        status = enrollment_request['status']
        course_enrollment = None
        if program_enrollment.user:
            course_enrollment = CourseEnrollment.enroll(
                program_enrollment.user,
                self.course,
                mode=CourseMode.MASTERS,
                check_access=True,
            )
            if status == CourseEnrollmentResponseStatuses.INACTIVE:
                course_enrollment.deactivate()

        ProgramCourseEnrollment.objects.create(
            program_enrollment=program_enrollment,
            course_enrollment=course_enrollment,
            course_key=self.course,
            status=status,
        )
        return status

    def get_existing_program_enrollments(self, enrollments):
        """
        Parameters:
            - enrollments: A list of enrollment requests
        Returns:
            - Dictionary mapping all student keys in the enrollment requests
              to that user's existing program entrollment <self.program>
        """
        external_user_keys = enrollments.map(lambda e: e['student_key'])
        existing_enrollments = ProgramEnrollment.objects.filter(external_user_key__in=external_user_keys)
        existing_enrollments = existing_enrollments.select_related('program_course_enrollment')
        return existing_enrollments.in_bulk(enrollments, field_name)