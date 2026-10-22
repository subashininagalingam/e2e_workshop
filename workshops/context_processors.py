from django.conf import settings


def site(request):
    return {"ORG": settings.ORG, "SITE_URL": settings.SITE_URL}
