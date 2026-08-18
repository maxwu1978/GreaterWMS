from django.contrib import admin
from django.conf import settings
from django.urls import path, include, re_path
from django.contrib.staticfiles.views import serve
from django.views.static import serve as static_serve
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.permissions import IsAuthenticated
from utils.auth import Authtication
from . import views


def return_static(request, path, insecure=True, **kwargs):
  return serve(request, path, insecure, **kwargs)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
    path('myip/', views.myip, name='myip'),
    path('health/', views.health, name='health'),
    path('health', views.health, name='health-no-slash'),
    path('cli/install/', views.cli_install, name='cli-install'),
    path('cli/download/', views.cli_download, name='cli-download'),
    path(
        'skills/wms-scheduled-email-intake/download/',
        views.email_intake_skill_download,
        name='scheduled-email-intake-skill-download',
    ),
    path(
        'skills/wms-email-intake-operator/download/',
        views.legacy_email_intake_skill_download,
        name='legacy-email-intake-skill-download',
    ),
    path('asn/', include('asn.urls')),
    path('asn/serial/', include('asnserial.urls')),
    path('dn/', include('dn.urls')),
    path('receiving/', include('receiving.urls')),
    path('transport/', include('transport.urls')),
    path('staff/', include('staff.urls')),
    path('binset/', include('binset.urls')),
    path('staging/', include('staging.urls')),
    path('binsize/', include('binsize.urls')),
    path('binproperty/', include('binproperty.urls')),
    path('capital/', include('capital.urls')),
    path('driver/', include('driver.urls')),
    path('stock/', include('stock.urls')),
    path('company/', include('company.urls')),
    path('cyclecount/', include('cyclecount.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('supplier/', include('supplier.urls')),
    path('customer/', include('customer.urls')),
    path('warehouse/', include('warehouse.urls')),
    path('goods/', include('goods.urls')),
    path('goodsunit/', include('goodsunit.urls')),
    path('goodsclass/', include('goodsclass.urls')),
    path('goodscolor/', include('goodscolor.urls')),
    path('goodsbrand/', include('goodsbrand.urls')),
    path('goodsshape/', include('goodsshape.urls')),
    path('goodsspecs/', include('goodsspecs.urls')),
    path('goodsorigin/', include('goodsorigin.urls')),
    path('scanner/', include('scanner.urls')),
    path('payment/', include('payment.urls')),
    path('login/', include('userlogin.urls')),
    path('register/', include('userregister.urls')),
    path('uploadfile/', include('uploadfile.urls')),
    path('tenant/', include('tenant_cleanup.urls')),
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    re_path(r'^favicon\.ico$', views.favicon, name='favicon'),
    re_path('^css/.*$', views.css, name='css'),
    re_path('^js/.*$', views.js, name='js'),
    re_path('^statics/.*$', views.statics, name='statics'),
    re_path('^fonts/.*$', views.fonts, name='fonts'),
    re_path(r'^robots.txt', views.robots, name='robots'),
    re_path(r'^media/(?P<path>.*)$', static_serve, {'document_root': settings.MEDIA_ROOT}),
    re_path(r'^static/(?P<path>.*)$', return_static, name='static')
]

urlpatterns += [
    path(
        'api/',
        SpectacularAPIView.as_view(
            authentication_classes=[Authtication],
            permission_classes=[IsAuthenticated],
        ),
        name='schema',
    ),
    # Optional UI:
    path(
        'api/debug/',
        SpectacularSwaggerView.as_view(
            url_name='schema',
            authentication_classes=[Authtication],
            permission_classes=[IsAuthenticated],
        ),
        name='swagger-ui',
    ),
    path(
        'api/docs/',
        SpectacularRedocView.as_view(
            url_name='schema',
            authentication_classes=[Authtication],
            permission_classes=[IsAuthenticated],
        ),
        name='docs',
    ),
]
