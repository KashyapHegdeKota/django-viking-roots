import json
import uuid
import os
import traceback
from datetime import datetime
from difflib import SequenceMatcher

from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import FileSystemStorage
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import User

# Import the NEW Schema
from .models import FamilyTree, TreeAccess, Location, Person, FamilyGroup, ChildLink, Event, Fact
from .services.gedcom_service import GedcomImportService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_user_for_request(request):
    """Temporary auth helper"""
    if request.user.is_authenticated:
        return request.user
    user, _ = User.objects.get_or_create(username='testuser')
    return user

def get_or_create_default_tree(user):
    """Bridges the gap until the UI supports selecting multiple trees."""
    access = TreeAccess.objects.filter(user=user, role='owner').first()
    if access:
        return access.tree
    tree = FamilyTree.objects.create(name=f"{user.username}'s Family Tree")
    TreeAccess.objects.create(user=user, tree=tree, role='owner')
    return tree

def _serialize_person(person):
    """
    Transforms the relational SQL structure into the flat node format
    expected by the React family-chart (f3) visualizer.
    """
    facts = [{'id': f.id, 'key': f.key, 'value': f.value} for f in person.facts.all()]
    
    # Resolve Spouses
    spouse_ids = []
    for fam in person.families_as_husband.select_related('wife'):
        if fam.wife: spouse_ids.append(str(fam.wife.id))
    for fam in person.families_as_wife.select_related('husband'):
        if fam.husband: spouse_ids.append(str(fam.husband.id))
        
    # Resolve Parents
    father_id = mother_id = None
    parent_link = person.parent_family_links.select_related('family__husband', 'family__wife').first()
    if parent_link:
        if parent_link.family.husband: father_id = str(parent_link.family.husband.id)
        if parent_link.family.wife: mother_id = str(parent_link.family.wife.id)
        
    # Resolve Children
    child_ids = []
    for fam in person.families_as_husband.prefetch_related('children_links__child'):
        child_ids.extend([str(link.child.id) for link in fam.children_links.all()])
    for fam in person.families_as_wife.prefetch_related('children_links__child'):
        child_ids.extend([str(link.child.id) for link in fam.children_links.all()])

    full_name = f"{person.first_name} {person.last_name}".strip()

    # Find birth/death events for quick data
    birth = person.events.filter(event_type='BIRT').select_related('location').first()
    death = person.events.filter(event_type='DEAT').select_related('location').first()

    return {
        'id':                str(person.id),
        'name':              full_name or "Unknown",
        'first_name':        person.first_name,
        'last_name':         person.last_name,
        'gender':            person.gender,
        'birth_year':        person.birth_year,
        'birth_date':        birth.parsed_date.isoformat() if birth and birth.parsed_date else None,
        'death_year':        person.death_year,
        'death_date':        death.parsed_date.isoformat() if death and death.parsed_date else None,
        'birth_location':    birth.location.name if birth and birth.location else None,
        'facts':             facts,
        
        # Extracted Relational Links for f3 chart
        'father_id':         father_id,
        'mother_id':         mother_id,
        'spouse_ids':        list(set(spouse_ids)),
        'child_ids':         list(set(child_ids)),
    }

def _resolve_location(location_name):
    if not location_name or not location_name.strip():
        return None
    loc, _ = Location.objects.get_or_create(name=location_name.strip())
    return loc

# ---------------------------------------------------------------------------
# Data retrieval
# ---------------------------------------------------------------------------

@csrf_exempt
def get_family_tree(request):
    """Provides data formatted for the f3 React Chart"""
    if request.method == 'GET':
        try:
            user = get_user_for_request(request)
            tree = get_or_create_default_tree(user)
            people = Person.objects.filter(tree=tree).prefetch_related(
                'facts', 'events__location',
                'families_as_husband__wife', 'families_as_wife__husband',
                'families_as_husband__children_links__child', 
                'families_as_wife__children_links__child',
                'parent_family_links__family__husband', 'parent_family_links__family__wife'
            )
            return JsonResponse({
                'tree': [_serialize_person(p) for p in people],
                'total_ancestors': people.count(),
            }, status=200)
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def get_timeline_data(request):
    """SPONSOR REQUIREMENT: Left-Aligned Chronological Timeline."""
    if request.method == 'GET':
        try:
            user = get_user_for_request(request)
            tree = get_or_create_default_tree(user)
            
            # Fetch all events on this tree ordered by parsed date/string
            events = Event.objects.filter(tree=tree).select_related('person', 'family', 'location')
            
            timeline_events = []
            for evt in events:
                # We need a display name. If it's a person event, use person name. 
                # If family event (marriage), combine names.
                title = evt.event_type
                desc = ""
                year = evt.parsed_date.year if evt.parsed_date else None

                if evt.person:
                    person_name = f"{evt.person.first_name} {evt.person.last_name}".strip()
                    title = f"{evt.event_type} of {person_name}"
                    if evt.location: desc = f"In {evt.location.name}"
                elif evt.family:
                    h_name = f"{evt.family.husband.first_name}" if evt.family.husband else "Unknown"
                    w_name = f"{evt.family.wife.first_name}" if evt.family.wife else "Unknown"
                    title = f"{evt.event_type} of {h_name} & {w_name}"
                    if evt.location: desc = f"In {evt.location.name}"

                # Only include events with dates in the timeline
                if evt.date_string or evt.parsed_date:
                    timeline_events.append({
                        'id':          f"evt_{evt.id}",
                        'year':        year,
                        'date':        evt.parsed_date.isoformat() if evt.parsed_date else evt.date_string,
                        'title':       title,
                        'description': desc,
                        'type':        evt.event_type.lower(),
                        'person_id':   str(evt.person.id) if evt.person else None,
                    })

            def sort_key(x):
                if x['date']: return str(x['date'])
                if x['year']: return f"{x['year']}-01-01"
                return "0000-00-00"

            timeline_events.sort(key=sort_key)
            return JsonResponse({'timeline': timeline_events}, status=200)
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


# ---------------------------------------------------------------------------
# GEDCOM import & export
# ---------------------------------------------------------------------------

@csrf_exempt
def upload_gedcom(request):
    if request.method == 'POST' and request.FILES.get('file'):
        try:
            user = get_user_for_request(request)
            gedcom_file = request.FILES['file']
            fs = FileSystemStorage()
            filename = fs.save(gedcom_file.name, gedcom_file)
            file_path = fs.path(filename)
            
            importer = GedcomImportService(user)
            # This now creates the new tree and relational links
            tree = importer.process_gedcom_file(file_path, gedcom_file.name)
            
            os.remove(file_path)
            return JsonResponse({'success': True, 'message': f'Successfully imported {tree.name}'}, status=200)
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'No file uploaded'}, status=400)


@csrf_exempt
def export_gedcom(request):
    if request.method == 'GET':
        try:
            user = get_user_for_request(request)
            tree = get_or_create_default_tree(user)
            
            export_service = GedcomExportService(user, tree.id)
            gedcom_string = export_service.generate_gedcom()
            
            response = HttpResponse(gedcom_string, content_type='text/plain')
            filename = f"VikingRoots_{user.username}_{datetime.now().strftime('%Y%m%d')}.ged"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
            
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


# ---------------------------------------------------------------------------
# Locations 
# ---------------------------------------------------------------------------

@csrf_exempt
def locations(request):
    if request.method == 'GET':
        query = request.GET.get('search', '').strip()
        qs = Location.objects.all()
        if query:
            qs = qs.filter(name__icontains=query)
        return JsonResponse({
            'locations': [
                {'id': loc.id, 'name': loc.name, 'latitude': loc.latitude, 'longitude': loc.longitude}
                for loc in qs[:20]
            ]
        }, status=200)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name', '').strip()
            if not name: return JsonResponse({'error': 'name is required'}, status=400)
            
            loc, created = Location.objects.get_or_create(
                name=name,
                defaults={'latitude': data.get('latitude'), 'longitude': data.get('longitude')}
            )
            return JsonResponse({'id': loc.id, 'name': loc.name, 'created': created}, status=201 if created else 200)
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


# ---------------------------------------------------------------------------
# Person CRUD (Manual Entry)
# ---------------------------------------------------------------------------

@csrf_exempt
def check_duplicates(request):
    if request.method == 'GET':
        user = get_user_for_request(request)
        tree = get_or_create_default_tree(user)
        name = request.GET.get('name', '').strip()
        if not name: return JsonResponse({'duplicates': []}, status=200)
        
        candidates = []
        for person in Person.objects.filter(tree=tree, first_name__icontains=name.split()[0]):
            full_name = f"{person.first_name} {person.last_name}".strip()
            score = SequenceMatcher(None, name.lower(), full_name.lower()).ratio()
            if score >= 0.82:
                candidates.append({
                    'id': str(person.id), 'name': full_name,
                    'birth_year': person.birth_year, 'score': round(score, 2),
                })
        return JsonResponse({'duplicates': sorted(candidates, key=lambda x: x['score'], reverse=True)}, status=200)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def create_ancestor(request):
    if request.method != 'POST': return JsonResponse({'error': 'Invalid request method'}, status=405)
    try:
        user = get_user_for_request(request)
        tree = get_or_create_default_tree(user)
        data = json.loads(request.body)

        name = data.get('name', 'Unknown Ancestor').strip()
        parts = name.split(' ', 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""
        
        birth_year = data.get('birth_year')

        person = Person.objects.create(
            tree=tree,
            first_name=first_name,
            last_name=last_name,
            gender=data.get('gender', 'U'),
            birth_year=int(birth_year) if birth_year else None,
            death_year=int(data.get('death_year')) if data.get('death_year') else None,
        )

        for fact in data.get('facts', []):
            if fact.get('key') and fact.get('value'):
                Fact.objects.create(person=person, key=fact['key'], value=fact['value'])

        location = _resolve_location(data.get('birth_location_name'))
        birth_date = None
        if data.get('birth_date'):
            try: birth_date = datetime.strptime(data['birth_date'], '%Y-%m-%d').date()
            except ValueError: pass

        if birth_date or birth_year or location:
            Event.objects.create(
                tree=tree, person=person, event_type='BIRT',
                date_string=data.get('birth_date') or str(birth_year or ''),
                parsed_date=birth_date, location=location
            )

        return JsonResponse({
            'success': True,
            'ancestor': _serialize_person(person),
        }, status=201)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def manage_ancestor(request, ancestor_id):
    user = get_user_for_request(request)
    tree = get_or_create_default_tree(user)
    try:
        person = Person.objects.get(id=ancestor_id, tree=tree)
    except (Person.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Person not found'}, status=404)

    if request.method == 'GET':
        return JsonResponse({'ancestor': _serialize_person(person)}, status=200)

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            if 'name' in data:
                parts = data['name'].strip().split(' ', 1)
                person.first_name = parts[0]
                person.last_name = parts[1] if len(parts) > 1 else ""
            if 'gender' in data: person.gender = data['gender']
            if 'birth_year' in data: person.birth_year = data['birth_year']
            if 'death_year' in data: person.death_year = data['death_year']
            person.save()

            return JsonResponse({'success': True, 'ancestor': _serialize_person(person)}, status=200)
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)

    if request.method == 'DELETE':
        person.delete()
        return JsonResponse({'success': True, 'message': 'Person deleted'}, status=200)

    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def manage_ancestor_facts(request, ancestor_id):
    user = get_user_for_request(request)
    tree = get_or_create_default_tree(user)
    try:
        person = Person.objects.get(id=ancestor_id, tree=tree)
    except (Person.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Person not found'}, status=404)

    if request.method == 'GET':
        return JsonResponse({'facts': [{'id': f.id, 'key': f.key, 'value': f.value} for f in person.facts.all()]}, status=200)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            if not data.get('key') or not data.get('value'):
                return JsonResponse({'error': 'Both key and value required'}, status=400)
            fact = Fact.objects.create(person=person, key=data['key'].strip(), value=data['value'].strip())
            return JsonResponse({'success': True, 'fact': {'id': fact.id, 'key': fact.key, 'value': fact.value}}, status=201)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)

@csrf_exempt
def manage_single_fact(request, ancestor_id, fact_id):
    """
    PUT    /heritage/ancestor/<id>/facts/<fact_id>/
    DELETE /heritage/ancestor/<id>/facts/<fact_id>/
    """
    user = get_user_for_request(request)
    tree = get_or_create_default_tree(user)
    try:
        person = Person.objects.get(id=ancestor_id, tree=tree)
        fact = Fact.objects.get(pk=fact_id, person=person)
    except (Person.DoesNotExist, Fact.DoesNotExist):
        return JsonResponse({'error': 'Not found'}, status=404)

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            if 'key' in data: fact.key = data['key'].strip()
            if 'value' in data: fact.value = data['value'].strip()
            fact.save()
            return JsonResponse({'success': True, 'fact': {'id': fact.id, 'key': fact.key, 'value': fact.value}})
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)

    if request.method == 'DELETE':
        fact.delete()
        return JsonResponse({'success': True, 'message': 'Fact deleted'}, status=200)

    return JsonResponse({'error': 'Invalid request method'}, status=405)


# ---------------------------------------------------------------------------
# Person ↔ Event linking 
# ---------------------------------------------------------------------------

@csrf_exempt
def manage_ancestor_events(request, ancestor_id):
    """
    GET  /heritage/ancestor/<id>/events/
    POST /heritage/ancestor/<id>/events/
    """
    user = get_user_for_request(request)
    tree = get_or_create_default_tree(user)
    try:
        person = Person.objects.get(id=ancestor_id, tree=tree)
    except (Person.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Person not found'}, status=404)

    if request.method == 'GET':
        data = [
            {
                'event_id': evt.id,
                'event_type': evt.event_type,
                'date': evt.parsed_date.isoformat() if evt.parsed_date else evt.date_string,
                'location': evt.location.name if evt.location else None,
            }
            for evt in person.events.select_related('location').all()
        ]
        return JsonResponse({'events': data}, status=200)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            parsed_date = None
            if data.get('date'):
                try: parsed_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
                except ValueError: pass

            event = Event.objects.create(
                tree=tree, 
                person=person,
                event_type=data.get('event_type', 'PERS'),
                date_string=data.get('date_string', data.get('date', '')),
                parsed_date=parsed_date,
                location=_resolve_location(data.get('location_name'))
            )
            return JsonResponse({'success': True, 'event_id': event.id}, status=201)
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=405)


# ---------------------------------------------------------------------------
# Events Edit/Delete
# ---------------------------------------------------------------------------

@csrf_exempt
def manage_event(request, event_id):
    user = get_user_for_request(request)
    tree = get_or_create_default_tree(user)
    
    try:
        event = Event.objects.get(id=event_id, tree=tree)
    except Event.DoesNotExist:
        return JsonResponse({'error': 'Event not found or permission denied'}, status=404)

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            if 'event_type' in data: event.event_type = data['event_type']
            if 'location_name' in data: event.location = _resolve_location(data['location_name'])
            
            if 'date' in data:
                try: 
                    event.parsed_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
                    event.date_string = data['date']
                except ValueError: 
                    event.parsed_date = None
                    event.date_string = data['date']
                    
            event.save()
            return JsonResponse({'success': True, 'message': 'Event updated'})
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)

    if request.method == 'DELETE':
        event.delete()
        return JsonResponse({'success': True, 'message': 'Event deleted'})

    return JsonResponse({'error': 'Invalid request method'}, status=405)