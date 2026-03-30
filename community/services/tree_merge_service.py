from django.db.models import Q

# CROSS APP IMPORTS
from heritage.models import Ancestor
from community.models import AncestorMatch, MergedFamilyTree

class FamilyTreeMergeService:
    def __init__(self, users):
        self.users = users
    
    def build_merged_tree(self):
        merged_tree = {'nodes': [], 'edges': [], 'clusters': {}}
        processed, ancestor_map = set(), {}
        all_ancestors = Ancestor.objects.filter(user__in=self.users).prefetch_related('facts', 'stories', 'media_tags__media', 'events__event')
        confirmed_matches = AncestorMatch.objects.filter(status='confirmed').filter(Q(ancestor1__user__in=self.users) & Q(ancestor2__user__in=self.users))
        
        match_groups = {}
        for match in confirmed_matches:
            id1, id2 = match.ancestor1.id, match.ancestor2.id
            group_id = next((gid for gid, members in match_groups.items() if id1 in members or id2 in members), None)
            if group_id: match_groups[group_id].update([id1, id2])
            else: match_groups[id1] = {id1, id2}
        
        for ancestor in all_ancestors:
            merged_id = next((f"merged_{gid}" for gid, mems in match_groups.items() if ancestor.id in mems), f"single_{ancestor.id}")
            if merged_id in processed:
                ancestor_map[merged_id].append(ancestor)
                continue
            processed.add(merged_id)
            ancestor_map[merged_id] = [ancestor]
            
            merged_data = self.merge_ancestor_data(ancestor_map[merged_id])
            merged_tree['nodes'].append({
                'id': merged_id, 'name': merged_data['name'], 'birth_year': merged_data['birth_year'], 'death_year': merged_data['death_year'],
                'origin': merged_data['origin'], 'facts': merged_data['facts'], 'stories': merged_data['stories'], 'events': merged_data['events'],
                'contributors': [{'user': a.user.username, 'relation_to_user': a.relation} for a in ancestor_map[merged_id]],
                'photo_urls': merged_data['photos']
            })
        
        merged_tree['edges'] = self.infer_relationships(merged_tree['nodes'])
        return merged_tree
    
    def merge_ancestor_data(self, ancestors):
        merged = {'name': ancestors[0].name, 'birth_year': None, 'death_year': None, 'origin': None, 'facts': {}, 'stories': [], 'photos': [], 'events': []}
        for ancestor in ancestors:
            if not merged['birth_year'] and ancestor.birth_year: merged['birth_year'] = ancestor.birth_year
            if not merged['death_year'] and ancestor.death_year: merged['death_year'] = ancestor.death_year
            if not merged['origin'] and ancestor.origin: merged['origin'] = ancestor.origin
            
            for fact in ancestor.facts.all():
                if fact.key not in merged['facts']: merged['facts'][fact.key] = []
                merged['facts'][fact.key].append({'value': fact.value, 'source': ancestor.user.username})
            for story in ancestor.stories.all(): merged['stories'].append({'content': story.content, 'author': ancestor.user.username})
            for tag in ancestor.media_tags.all():
                if tag.media.media_type == 'photo': merged['photos'].append(tag.media.file.url)
            for participation in ancestor.events.all():
                evt = participation.event
                merged['events'].append({'title': evt.title, 'date': evt.date_start.isoformat() if evt.date_start else None, 'location': evt.location.name if evt.location else None, 'type': evt.event_type})
        
        merged['photos'] = list(set(merged['photos']))
        merged['events'] = [dict(t) for t in {tuple(d.items()) for d in merged['events']}]
        return merged
    
    def infer_relationships(self, nodes):
        edges = []
        for node in nodes:
            for contributor in node['contributors']:
                relation = contributor['relation_to_user'].lower()
                if 'father' in relation or 'mother' in relation:
                    for other_node in nodes:
                        if other_node['id'] == node['id']: continue
                        for other_contrib in other_node['contributors']:
                            other_rel = other_contrib['relation_to_user'].lower()
                            if ('grandfather' in other_rel or 'grandmother' in other_rel) and contributor['user'] == other_contrib['user']:
                                edges.append({'from': other_node['id'], 'to': node['id'], 'type': 'parent-child'})
        return edges
    
    def save_merged_tree(self, name, created_by):
        tree = MergedFamilyTree.objects.create(name=name, created_by=created_by)
        tree.members.set(self.users)
        return tree