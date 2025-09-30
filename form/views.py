from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages

# Create your views here.
def register_new_user(req):
    if req.method == 'POST':
        username = req.POST.get('username')
        email = req.POST.get('email')
        password = req.POST.get('password')
        confirm_password = req.POST.get('confirm_password')

        if password != confirm_password:
            messages.error(req, "Passwords do not match.")
            return redirect('register')
        
        if User.objects.filter(username=username).exists():
            messages.error(req, "Username already taken.")
            return redirect('register')
        
        if User.objects.filter(email=email).exists():
            messages.error(req, "Email already registered.")
            return redirect('register') 
        user = User.objects.create_user(username=username, email=email, password=password)
        login(req, user)
        return redirect('login')
    return render(req, 'form/register.html')

def login_existing_user(req):
    if req.method == 'POST':
        username = req.POST.get('username')
        password = req.POST.get('password')

        user = authenticate(req, username=username, password=password)
        if user is not None:
            login(req, user)
            return redirect('home')
        else:
            messages.error(req, "Invalid username or password.")
            return redirect('login')
    return render(req, 'form/login.html')

def logout_user(req):
    logout(req)
    return redirect('login')
