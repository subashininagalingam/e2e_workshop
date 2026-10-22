from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve
from django.conf import settings

admin.site.site_header = "Errors2Experts Workshops Admin"
admin.site.site_title = "E2E Admin"
admin.site.index_title = "Manage workshops"

urlpatterns = [
    path("admin/", admin.site.urls),
    # Poster images. Fine for a small site; use a CDN or web-server mapping for heavy traffic.
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    path("", include("workshops.urls")),
]
