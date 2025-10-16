from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
import json

@csrf_exempt
def register_new_user(req):
    if req.method == 'POST':
        data = json.loads(req.body)
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        confirm_password = data.get('confirm_password')

        if password != confirm_password:
            return JsonResponse({'error': 'Passwords do not match'}, status=400)

        if User.objects.filter(username=username).exists():
            return JsonResponse({'error': 'Username already taken'}, status=400)

        if User.objects.filter(email=email).exists():
            return JsonResponse({'error': 'Email already registered'}, status=400)

        user = User.objects.create_user(username=username, email=email, password=password)
        return JsonResponse({'message': 'User registered successfully'}, status=201)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def login_existing_user(req):
    if req.method == 'POST':
        data = json.loads(req.body)
        username = data.get('username')
        password = data.get('password')
        user = authenticate(req, username=username, password=password)

        if user is not None:
            login(req, user)
            return JsonResponse({'message': 'Login successful'})
        else:
            return JsonResponse({'error': 'Invalid credentials'}, status=401)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def logout_user(req):
    logout(req)
<<<<<<< HEAD
    return JsonResponse({'message': 'Logged out'})
=======
    return redirect('login')
    
>>>>>>> 24156441b1f54135b072a92067383c02310732a8
