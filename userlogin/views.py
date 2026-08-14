from django.http import JsonResponse
from utils.fbmsg import FBMsg
from django.contrib import auth
from django.contrib.auth.models import User
from django.views.decorators.csrf import csrf_exempt
import json
from userprofile.models import Users
from staff.models import ListModel as staff
from staff.auth import issue_session_token

@csrf_exempt
def login(request, *args, **kwargs):
    if request.method != 'POST':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    try:
        post_data = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'detail': 'Request body must be valid JSON'}, status=400)

    if not isinstance(post_data, dict):
        return JsonResponse({'detail': 'Request body must be a JSON object'}, status=400)

    data = {
        "name": post_data.get('name'),
        "password": post_data.get('password'),
    }
    ip = request.META.get('HTTP_X_FORWARDED_FOR') if request.META.get(
        'HTTP_X_FORWARDED_FOR') else request.META.get('REMOTE_ADDR')
    if not data['name'] or not data['password']:
        return JsonResponse({'detail': 'Username and password are required'}, status=400)

    if User.objects.filter(username=str(data['name'])).exists():
        user = auth.authenticate(username=str(data['name']), password=str(data['password']))
        if user is None:
            err_ret = FBMsg.err_ret()
            err_ret['ip'] = ip
            return JsonResponse(err_ret, status=401)
        else:
            user_detail = Users.objects.filter(user_id=user.id).first()
            staff_detail = staff.objects.filter(
                openid=user_detail.openid,
                staff_name=str(user_detail.name),
                staff_type__iexact='Admin',
                is_delete=False,
            ).first() if user_detail else None
            if user_detail is None or staff_detail is None:
                return JsonResponse({'detail': 'User profile is not configured'}, status=500)
            if staff_detail.is_lock:
                return JsonResponse(
                    {
                        'detail': (
                            'Administrator account is locked. '
                            'Please contact the administrator'
                        )
                    },
                    status=423,
                )
            api_token = issue_session_token(staff_detail, token_kind='admin')
            data = {
                "name": data['name'],
                # ``openid`` is retained as the frontend's historical token
                # field; it now contains an opaque session token, not the
                # tenant identifier.
                'openid': api_token,
                'token': api_token,
                'tenant_openid': user_detail.openid,
                "user_id": staff_detail.id,
                "staff_type": staff_detail.staff_type,
            }
            ret = FBMsg.ret()
            ret['ip'] = ip
            ret['data'] = data
            return JsonResponse(ret)
    else:
        err_ret = FBMsg.err_ret()
        err_ret['ip'] = ip
        return JsonResponse(err_ret, status=401)
