import django_filters
from apps.academics.models import Department, Course
from apps.accounts.models import User
from .models import ForumThread


class ForumThreadFilter(django_filters.FilterSet):
    department = django_filters.ModelMultipleChoiceFilter(
        field_name="department__short_code",
        to_field_name="short_code",
        queryset=Department.objects.all(),
        conjoined=False,  # OR logic — match any selected department
    )
    course = django_filters.ModelMultipleChoiceFilter(
        field_name="course__code",
        to_field_name="code",
        queryset=Course.objects.all(),
        conjoined=False,
    )
    user = django_filters.ModelMultipleChoiceFilter(
        field_name="author__handle",
        to_field_name="handle",
        queryset=User.objects.all(),
        conjoined=False,
    )

    class Meta:
        model = ForumThread
        fields = ["department", "course", "user"]
