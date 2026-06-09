from django.db import models
from django.core.exceptions import ValidationError


class Department(models.Model):
    name = models.CharField(max_length=100, db_index=True)
    short_code = models.CharField(max_length=10, unique=True, db_index=True)

    def save(self, *args, **kwargs):
        self.short_code = self.short_code.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Course(models.Model):
    name = models.CharField(max_length=100, db_index=True)
    code = models.CharField(max_length=20, unique=True, db_index=True)
    department = models.ForeignKey(
        Department, on_delete=models.CASCADE, related_name="courses"
    )

    def save(self, *args, **kwargs):
        self.code = self.code.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Section(models.Model):
    name = models.CharField(max_length=2, unique=True)

    def save(self, *args, **kwargs):
        self.name = self.name.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Trimester(models.Model):
    code = models.PositiveIntegerField(unique=True)  # e.g. 241

    TERM_MAP = {
        1: "Spring",
        2: "Summer",
        3: "Fall",
    }

    def get_term(self):
        return self.TERM_MAP.get(self.code % 10, "Unknown")

    def get_term_number(self):
        return self.code % 10

    def get_year(self):
        return 2000 + (self.code // 10)

    def get_trimester_name(self):
        term = self.get_term()
        return f"{term} {self.get_year()}"

    def clean(self):
        term = self.get_term_number()

        if term not in self.TERM_MAP:
            raise ValidationError(
                "Invalid trimester code. Last digit must be 1, 2, or 3."
            )

    def __str__(self):
        return self.get_trimester_name()


# class UserAdmission(models.Model):
#     user = models.ForeignKey(
#         settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="admissions"
#     )
#     department = models.ForeignKey(
#         Department, on_delete=models.CASCADE, related_name="admissions"
#     )
#     trimester = models.ForeignKey(
#         Trimester, on_delete=models.CASCADE, related_name="admissions"
#     )

#     def __str__(self):
#         return (
#             f"{self.user.email} - {self.department.short_code} ({self.trimester.name})"
#         )


# class UserCourseEnrollmentStatus(models.Model):
#     name = models.CharField(max_length=50)

#     def save(self, *args, **kwargs):
#         self.name = self.name.upper()
#         super().save(*args, **kwargs)

#     def __str__(self):
#         return self.name


# class UserCourseEnrollment(models.Model):
#     user = models.ForeignKey(
#         settings.AUTH_USER_MODEL,
#         on_delete=models.CASCADE,
#         related_name="course_enrollments",
#     )
#     course = models.ForeignKey(
#         Course, on_delete=models.CASCADE, related_name="enrollments"
#     )
#     section = models.ForeignKey(
#         Section, on_delete=models.CASCADE, related_name="enrollments"
#     )
#     trimester = models.ForeignKey(
#         Trimester, on_delete=models.CASCADE, related_name="course_enrollments"
#     )
#     status = models.ForeignKey(
#         UserCourseEnrollmentStatus,
#         on_delete=models.PROTECT,
#         related_name="course_enrollments",
#     )

#     def __str__(self):
#         return f"{self.user.email} - {self.course.code} ({self.trimester.name})"
