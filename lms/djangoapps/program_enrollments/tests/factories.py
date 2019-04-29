import factory
from factory.fuzzy import FuzzyChoice, FuzzyDateTime, FuzzyDecimal, FuzzyInteger, FuzzyText

from program_enrollments.models import ProgramCourseEnrollment, ProgramEnrollment
from student.tests.factories import UserFactory, CourseEnrollmentFactory


class ProgramEnrollmentFactory(factory.DjangoModelFactory):
    class Meta:
        model = ProgramEnrollment

    external_user_key = FuzzyText(length=16)
    program_uuid = factory.LazyFunction(uuid4)
    curriculum_uuid = factory.LazyFunction(uuid4)
    status = "enrolled"


class ProgramCourseEnrollmentFactory(factory.DjangoModelFactory):
    class Meta:
        model = ProgramCourseEnrollment

    program_enrollment = factory.SubFactory(ProgramEnrollmentFactory)
    course_enrollment = factory.SubFactory(CourseEnrollmentFactory)
    course_key = CourseKey.from_string("test/testCourse")
    status = "active"

