import json
import uuid
import os
import traceback
from datetime import datetime
from difflib import SequenceMatcher

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import FileSystemStorage
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import User

from .models import Ancestor, AncestorFact, HeritageEvent, HeritageLocation, EventParticipation
from .services.db_storage import DatabaseStorageService
from .services.gedcom_service import GedcomImportService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_user_for_request(request):
    if request.user.is_authenticated:
        return request.user
    user, _ = User.objects.get_or_create(username='testuser')
    return user


def _serialize_ancestor(ancestor):
    facts = [{'id': f.id, 'key': f.key, 'value': f.value} for f in ancestor.facts.all()]
    photos = [
        {'url': tag.media.file.url, 'title': tag.media.title,
         'box_x': tag.box_x, 'box_y': tag.box_y}
        for tag in ancestor.media_tags.all()
    ]
    return {
        'id':                ancestor.unique_id,
        'name':              ancestor.name,
        'relation':          ancestor.relation,
        'gender':            ancestor.gender,
        'birth_year':        ancestor.birth_year,
        'birth_date':        ancestor.birth_date.isoformat() if ancestor.birth_date else None,
        'death_year':        ancestor.death_year,
        'death_date':        ancestor.death_date.isoformat() if ancestor.death_date else None,
        'origin':            ancestor.origin,
        'birth_location':    ancestor.birth_location.name if ancestor.birth_location else None,
        'birth_location_id': ancestor.birth_location.id if ancestor.birth_location else None,
        'source_type':       ancestor.source_type,
        'facts':             facts,
        'photos':            photos,
    }


def _resolve_location(location_name):
    if not location_name or not location_name.strip():
        return None
    loc, _ = HeritageLocation.objects.get_or_create(
        name=location_name.strip(),
        defaults={'location_type': 'other'}
    )
    return loc


def _find_duplicate_candidates(user, name, birth_year=None, threshold=0.82):
    candidates = []
    for anc in Ancestor.objects.filter(user=user).only('unique_id', 'name', 'birth_year', 'relation'):
        score = SequenceMatcher(None, name.lower().strip(), anc.name.lower().strip()).ratio()
        if score >= threshold:
            candidates.append({
                'id':         anc.unique_id,
                'name':       anc.name,
                'birth_year': anc.birth_year,
                'relation':   anc.relation,
                'score':      round(score, 2),
            })
    return sorted(candidates, key=lambda x: x['score'], reverse=True)


# ---------------------------------------------------------------------------
# Data retrieval
# ---------------------------------------------------------------------------

@csrf_exempt
def get_heritage_data(request):
    if request.method == 'GET':
        try:
            user = get_user_for_request(request)
            storage = DatabaseStorageService(user)
            return JsonResponse(storage.get_all_heritage_data(), status=200)
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def get_family_tree(request):
    if request.method == 'GET':
        try:
            user = get_user_for_request(request)
            ancestors = Ancestor.objects.filter(user=user).prefetch_related('facts', 'media_tags__media')
            return JsonResponse({
                'tree':            [_serialize_ancestor(a) for a in ancestors],
                'total_ancestors': ancestors.count(),
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
            ancestors = (
                Ancestor.objects
                .filter(user=user)
                .exclude(birth_year__isnull=True)
                .prefetch_related('events__event')
            )
            timeline_events = []
            for anc in ancestors:
                timeline_events.append({
                    'id':          f"{anc.unique_id}_birth",
                    'year':        anc.birth_year,
                    'date':        anc.birth_date.isoformat() if anc.birth_date else None,
                    'title':       f"Birth of {anc.name}",
                    'description': f"Born in {anc.birth_location.name if anc.birth_location else anc.origin or 'Unknown'}",
                    'type':        'birth',
                    'person_id':   anc.unique_id,
                })
                if anc.death_year:
                    timeline_events.append({
                        'id':        f"{anc.unique_id}_death",
                        'year':      anc.death_year,
                        'date':      anc.death_date.isoformat() if anc.death_date else None,
                        'title':     f"Passing of {anc.name}",
                        'type':      'death',
                        'person_id': anc.unique_id,
                    })
                for participation in anc.events.all():
                    evt = participation.event
                    timeline_events.append({
                        'id':          f"evt_{evt.id}_{anc.id}",
                        'year':        evt.date_start.year if evt.date_start else None,
                        'date':        evt.date_start.isoformat() if evt.date_start else None,
                        'title':       evt.title,
                        'description': f"{anc.name} was a {participation.role}",
                        'type':        'event',
                        'person_id':   anc.unique_id,
                    })

            def sort_key(x):
                if x['date']: return x['date']
                if x['year']: return f"{x['year']}-01-01"
                return "0000-00-00"

            timeline_events.sort(key=sort_key)
            return JsonResponse({'timeline': timeline_events}, status=200)
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


# ---------------------------------------------------------------------------
# GEDCOM import
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
            batch = importer.process_gedcom_file(file_path, gedcom_file.name)
            os.remove(file_path)
            return JsonResponse({'success': True, 'message': f'Successfully processed {batch.filename}'}, status=200)
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'No file uploaded'}, status=400)


# ---------------------------------------------------------------------------
# Locations  (NEW)
# ---------------------------------------------------------------------------

@csrf_exempt
def locations(request):
    """
    GET  /heritage/locations/?search=Gimli  — typeahead search.
    POST /heritage/locations/               — create a location explicitly.
    """
    if request.method == 'GET':
        query = request.GET.get('search', '').strip()
        qs = HeritageLocation.objects.all()
        if query:
            qs = qs.filter(name__icontains=query) | qs.filter(original_name__icontains=query)
        return JsonResponse({
            'locations': [
                {
                    'id':            loc.id,
                    'name':          loc.name,
                    'original_name': loc.original_name,
                    'location_type': loc.location_type,
                    'latitude':      loc.latitude,
                    'longitude':     loc.longitude,
                }
                for loc in qs[:20]
            ]
        }, status=200)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name', '').strip()
            if not name:
                return JsonResponse({'error': 'name is required'}, status=400)
            loc, created = HeritageLocation.objects.get_or_create(
                name=name,
                defaults={
                    'original_name': data.get('original_name', ''),
                    'location_type': data.get('location_type', 'other'),
                    'latitude':      data.get('latitude'),
                    'longitude':     data.get('longitude'),
                }
            )
            return JsonResponse({'id': loc.id, 'name': loc.name, 'created': created},
                                status=201 if created else 200)
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=405)


# ---------------------------------------------------------------------------
# Ancestor CRUD
# ---------------------------------------------------------------------------

@csrf_exempt
def check_duplicates(request):
    """
    GET /heritage/ancestors/check-duplicates/?name=Bjorn&birth_year=1890
    """
    if request.method == 'GET':
        user = get_user_for_request(request)
        name = request.GET.get('name', '').strip()
        if not name:
            return JsonResponse({'duplicates': []}, status=200)
        birth_year = request.GET.get('birth_year')
        try:
            birth_year = int(birth_year) if birth_year else None
        except ValueError:
            birth_year = None
        return JsonResponse({'duplicates': _find_duplicate_candidates(user, name, birth_year)}, status=200)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def create_ancestor(request):
    """
    POST /heritage/ancestors/

    Accepted fields:
        name, relation, gender
        birth_year, birth_date (YYYY-MM-DD)
        death_year, death_date (YYYY-MM-DD)
        birth_location_name   string — get_or_creates a HeritageLocation
        birth_location_id     int    — uses an existing HeritageLocation
        origin                legacy plain-text fallback
        facts                 list of {key, value}
        force                 bool — skip duplicate warning
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)
    try:
        user = get_user_for_request(request)
        data = json.loads(request.body)

        name       = data.get('name', 'Unknown Ancestor').strip()
        birth_year = data.get('birth_year')
        force      = data.get('force', False)

        if not force:
            try:
                by = int(birth_year) if birth_year else None
            except (ValueError, TypeError):
                by = None
            candidates = _find_duplicate_candidates(user, name, by)
            if candidates:
                return JsonResponse({
                    'warning':    'Possible duplicates found. Send with force=true to create anyway.',
                    'duplicates': candidates,
                }, status=409)

        location = None
        if data.get('birth_location_id'):
            try:
                location = HeritageLocation.objects.get(pk=data['birth_location_id'])
            except HeritageLocation.DoesNotExist:
                pass
        elif data.get('birth_location_name'):
            location = _resolve_location(data['birth_location_name'])

        birth_date = None
        if data.get('birth_date'):
            try:
                birth_date = datetime.strptime(data['birth_date'], '%Y-%m-%d').date()
                if not birth_year:
                    birth_year = birth_date.year
            except ValueError:
                pass

        death_date = None
        if data.get('death_date'):
            try:
                death_date = datetime.strptime(data['death_date'], '%Y-%m-%d').date()
            except ValueError:
                pass

        unique_id = data.get('id') or f"manual_{uuid.uuid4().hex[:8]}"
        ancestor = Ancestor.objects.create(
            user=user,
            unique_id=unique_id,
            name=name,
            relation=data.get('relation', ''),
            gender=data.get('gender', ''),
            birth_year=birth_year,
            birth_date=birth_date,
            death_year=data.get('death_year'),
            death_date=death_date,
            origin=data.get('origin') or '',
            birth_location=location,
            source_type='manual',
        )

        for fact in data.get('facts', []):
            key   = fact.get('key', '').strip()
            value = fact.get('value', '').strip()
            if key and value:
                AncestorFact.objects.create(ancestor=ancestor, key=key, value=value)

        if birth_date or birth_year:
            evt, _ = HeritageEvent.objects.get_or_create(
                title=f"Birth of {ancestor.name}",
                date_start=birth_date,
                defaults={'location': location, 'event_type': 'personal'}
            )
            EventParticipation.objects.get_or_create(
                event=evt, ancestor=ancestor, defaults={'role': 'Principal'}
            )

        return JsonResponse({
            'success':  True,
            'ancestor': _serialize_ancestor(
                Ancestor.objects.prefetch_related('facts', 'media_tags__media').get(pk=ancestor.pk)
            ),
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def manage_ancestor(request, ancestor_id):
    """
    GET    /heritage/ancestors/<id>/
    PUT    /heritage/ancestors/<id>/
    DELETE /heritage/ancestors/<id>/
    """
    user = get_user_for_request(request)
    try:
        ancestor = (
            Ancestor.objects
            .prefetch_related('facts', 'media_tags__media')
            .get(user=user, unique_id=ancestor_id)
        )
    except Ancestor.DoesNotExist:
        return JsonResponse({'error': 'Ancestor not found'}, status=404)

    if request.method == 'GET':
        return JsonResponse({'ancestor': _serialize_ancestor(ancestor)}, status=200)

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            if 'name'       in data: ancestor.name       = data['name']
            if 'relation'   in data: ancestor.relation   = data['relation']
            if 'gender'     in data: ancestor.gender     = data['gender']
            if 'birth_year' in data: ancestor.birth_year = data['birth_year']
            if 'death_year' in data: ancestor.death_year = data['death_year']
            if 'origin'     in data: ancestor.origin     = data['origin'] or ''

            if 'birth_date' in data:
                try:
                    ancestor.birth_date = datetime.strptime(data['birth_date'], '%Y-%m-%d').date()
                except ValueError:
                    ancestor.birth_date = None

            if 'death_date' in data:
                try:
                    ancestor.death_date = datetime.strptime(data['death_date'], '%Y-%m-%d').date()
                except ValueError:
                    ancestor.death_date = None

            if 'birth_location_id' in data:
                try:
                    ancestor.birth_location = HeritageLocation.objects.get(pk=data['birth_location_id'])
                except HeritageLocation.DoesNotExist:
                    pass
            elif 'birth_location_name' in data:
                ancestor.birth_location = _resolve_location(data['birth_location_name'])

            ancestor.save()
            return JsonResponse({
                'success':  True,
                'ancestor': _serialize_ancestor(
                    Ancestor.objects.prefetch_related('facts', 'media_tags__media').get(pk=ancestor.pk)
                ),
            }, status=200)
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)

    if request.method == 'DELETE':
        ancestor.delete()
        return JsonResponse({'success': True, 'message': 'Ancestor deleted'}, status=200)

    return JsonResponse({'error': 'Invalid request method'}, status=405)


# ---------------------------------------------------------------------------
# Ancestor Facts  (NEW)
# ---------------------------------------------------------------------------

@csrf_exempt
def manage_ancestor_facts(request, ancestor_id):
    """
    GET  /heritage/ancestors/<id>/facts/
    POST /heritage/ancestors/<id>/facts/
    """
    user = get_user_for_request(request)
    try:
        ancestor = Ancestor.objects.get(user=user, unique_id=ancestor_id)
    except Ancestor.DoesNotExist:
        return JsonResponse({'error': 'Ancestor not found'}, status=404)

    if request.method == 'GET':
        facts = [
            {'id': f.id, 'key': f.key, 'value': f.value}
            for f in ancestor.facts.all()
        ]
        return JsonResponse({'facts': facts}, status=200)

    if request.method == 'POST':
        try:
            data  = json.loads(request.body)
            key   = data.get('key', '').strip()
            value = data.get('value', '').strip()
            if not key or not value:
                return JsonResponse({'error': 'Both key and value are required'}, status=400)
            fact = AncestorFact.objects.create(ancestor=ancestor, key=key, value=value)
            return JsonResponse({
                'success': True,
                'fact': {'id': fact.id, 'key': fact.key, 'value': fact.value},
            }, status=201)
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def manage_single_fact(request, ancestor_id, fact_id):
    """
    PUT    /heritage/ancestors/<id>/facts/<fact_id>/
    DELETE /heritage/ancestors/<id>/facts/<fact_id>/
    """
    user = get_user_for_request(request)
    try:
        ancestor = Ancestor.objects.get(user=user, unique_id=ancestor_id)
        fact     = AncestorFact.objects.get(pk=fact_id, ancestor=ancestor)
    except (Ancestor.DoesNotExist, AncestorFact.DoesNotExist):
        return JsonResponse({'error': 'Not found'}, status=404)

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            if 'key'   in data: fact.key   = data['key'].strip()
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
# Ancestor ↔ Event linking  (NEW)
# ---------------------------------------------------------------------------

@csrf_exempt
def manage_ancestor_events(request, ancestor_id):
    """
    GET  /heritage/ancestors/<id>/events/
    POST /heritage/ancestors/<id>/events/   body: { event_id, role? }
    """
    user = get_user_for_request(request)
    try:
        ancestor = Ancestor.objects.get(user=user, unique_id=ancestor_id)
    except Ancestor.DoesNotExist:
        return JsonResponse({'error': 'Ancestor not found'}, status=404)

    if request.method == 'GET':
        data = [
            {
                'participation_id': p.id,
                'role':             p.role,
                'event': {
                    'id':         p.event.id,
                    'title':      p.event.title,
                    'date_start': p.event.date_start.isoformat() if p.event.date_start else None,
                    'event_type': p.event.event_type,
                    'location':   p.event.location.name if p.event.location else None,
                }
            }
            for p in ancestor.events.select_related('event__location').all()
        ]
        return JsonResponse({'events': data}, status=200)

    if request.method == 'POST':
        try:
            data     = json.loads(request.body)
            event_id = data.get('event_id')
            if not event_id:
                return JsonResponse({'error': 'event_id is required'}, status=400)
            event = get_object_or_404(HeritageEvent, pk=event_id)
            participation, created = EventParticipation.objects.get_or_create(
                event=event, ancestor=ancestor,
                defaults={'role': data.get('role', 'Principal')}
            )
            return JsonResponse({
                'success':          True,
                'created':          created,
                'participation_id': participation.id,
            }, status=201 if created else 200)
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=405)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@csrf_exempt
def manage_event(request, event_id):
    user = get_user_for_request(request)
    try:
        event = HeritageEvent.objects.get(id=event_id)
        if not event.participants.filter(ancestor__user=user).exists():
            return JsonResponse({'error': 'Permission denied'}, status=403)
    except HeritageEvent.DoesNotExist:
        return JsonResponse({'error': 'Event not found'}, status=404)

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            if 'title'       in data: event.title       = data['title']
            if 'description' in data: event.description = data['description']
            if 'event_type'  in data: event.event_type  = data['event_type']
            event.save()
            return JsonResponse({'success': True, 'message': 'Event updated'})
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)

    if request.method == 'DELETE':
        event.delete()
        return JsonResponse({'success': True, 'message': 'Event deleted'})

    return JsonResponse({'error': 'Invalid request method'}, status=405)