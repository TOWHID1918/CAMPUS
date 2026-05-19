"""
URL configuration for campus project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from campus.views import home

urlpatterns = [
    path("", home, name="home"),
    path("", include("apps.accounts.urls")),
    path("threads/", include("apps.threads.urls")),
    path("admin/", admin.site.urls),
    path("forum/", include("apps.forum.urls")),
    path("lost-found/", include("apps.lost_found.urls")),
    path("skill-exchange/", include("apps.skill_exchange.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("marketplace/", include("apps.marketplace.urls")),
    path("ride-share/", include("apps.ride_share.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
