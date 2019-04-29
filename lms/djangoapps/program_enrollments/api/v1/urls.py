""" Program Enrollments API v1 URLs. """
from django.conf import settings
from django.conf.urls import url

from lms.djangoapps.program_enrollments.api.v1.views import ProgramEnrollmentsView, ProgramCourseEnrollmentsView
from openedx.core.constants import COURSE_ID_PATTERN
from program_enrollments.api.v1.constants import PROGRAM_KEY_PATTERN


app_name = 'lms.djangoapps.program_enrollments'

urlpatterns = [
    url(
        r'^programs/{program_key}/enrollments/$'.format(program_key=r'.*'),
        ProgramEnrollmentsView.as_view(),
        name='course_grades'
    ),
    url(
        r'^programs/{program_key}/course/{course_id}/enrollments/'.format(program_key=PROGRAM_KEY_PATTERN, course_id=COURSE_ID_PATTERN),
        ProgramCourseEnrollmentsView.as_view(),
        name="program_course_enrollments"
    ),
]
