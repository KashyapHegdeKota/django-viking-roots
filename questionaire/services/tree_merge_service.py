# questionaire/services/tree_merge_service.py
from ..models import Ancestor, AncestorMatch, MergedFamilyTree
from django.db.models import Q


class FamilyTreeMergeService:
    """Combines multiple users' family trees into unified view"""
    
    def __init__(self, users):
        self.users = users
    
    def build_merged_tree(self):
        """
        Build a unified tree structure with deduplicated ancestors
        Returns: dict representing the merged tree
        """
        merged_tree = {
            'nodes': [],  # All unique people
            'edges': [],  # Relationships between people
            'clusters': {}  # Group by family branch
        }
        
        # Track processed ancestors to avoid duplicates
        processed = set()
        ancestor_map = {}  # Maps merged_id to list of original ancestors
        
        # Get all ancestors for these users
        all_ancestors = Ancestor.objects.filter(
            user__in=self.users
        ).prefetch_related('facts', 'stories')
        
        # Get confirmed matches
        confirmed_matches = AncestorMatch.objects.filter(
            status='confirmed'
        ).filter(
            Q(ancestor1__user__in=self.users) & Q(ancestor2__user__in=self.users)
        )
        
        # Build match groups (ancestors that are the same person)
        match_groups = {}
        for match in confirmed_matches:
            id1, id2 = match.ancestor1.id, match.ancestor2.id
            
            # Find existing group or create new one
            group_id = None
            for gid, members in match_groups.items():
                if id1 in members or id2 in members:
                    group_id = gid
                    break
            
            if group_id:
                match_groups[group_id].update([id1, id2])
            else:
                match_groups[id1] = {id1, id2}
        
        # Process each ancestor
        for ancestor in all_ancestors:
            # Check if this ancestor is part of a match group
            merged_id = None
            for group_id, members in match_groups.items():
                if ancestor.id in members:
                    merged_id = f"merged_{group_id}"
                    break
            
            if not merged_id:
                merged_id = f"single_{ancestor.id}"
            
            # Skip if already processed this merged entity
            if merged_id in processed:
                # Add contributor info
                ancestor_map[merged_id].append(ancestor)
                continue
            
            processed.add(merged_id)
            ancestor_map[merged_id] = [ancestor]
            
            # Merge data from all matching ancestors
            merged_data = self.merge_ancestor_data(ancestor_map[merged_id])
            
            node = {
                'id': merged_id,
                'name': merged_data['name'],
                'birth_year': merged_data['birth_year'],
                'death_year': merged_data['death_year'],
                'origin': merged_data['origin'],
                'facts': merged_data['facts'],
                'stories': merged_data['stories'],
                'contributors': [
                    {
                        'user': a.user.username,
                        'relation_to_user': a.relation
                    }
                    for a in ancestor_map[merged_id]
                ],
                'photo_urls': merged_data['photos']
            }
            
            merged_tree['nodes'].append(node)
        
        # Build relationships/edges (infer from relations)
        merged_tree['edges'] = self.infer_relationships(merged_tree['nodes'])
        
        return merged_tree
    
    def merge_ancestor_data(self, ancestors):
        """Merge data from multiple records of the same person"""
        # Take most complete data
        merged = {
            'name': ancestors[0].name,
            'birth_year': None,
            'death_year': None,
            'origin': None,
            'facts': {},
            'stories': [],
            'photos': []
        }
        
        for ancestor in ancestors:
            # Use first non-null value for each field
            if not merged['birth_year'] and ancestor.birth_year:
                merged['birth_year'] = ancestor.birth_year
            if not merged['death_year'] and ancestor.death_year:
                merged['death_year'] = ancestor.death_year
            if not merged['origin'] and ancestor.origin:
                merged['origin'] = ancestor.origin
            
            # Merge facts (combine from all sources)
            for fact in ancestor.facts.all():
                if fact.key not in merged['facts']:
                    merged['facts'][fact.key] = []
                merged['facts'][fact.key].append({
                    'value': fact.value,
                    'source': ancestor.user.username
                })
            
            # Collect all stories
            for story in ancestor.stories.all():
                merged['stories'].append({
                    'content': story.content,
                    'author': ancestor.user.username
                })
            
            # Collect photos
            for media in ancestor.media.filter(media_type='photo'):
                merged['photos'].append(media.file.url)
        
        return merged
    
    def infer_relationships(self, nodes):
        """Infer parent-child relationships from relation strings"""
        edges = []
        
        # Simple inference: if someone is "father" to userA and someone else
        # is "grandfather" to userA, they're parent-child
        
        # This is simplified - real implementation would need more logic
        for node in nodes:
            for contributor in node['contributors']:
                relation = contributor['relation_to_user'].lower()
                
                # Find parents (one generation up)
                if 'father' in relation or 'mother' in relation:
                    # Look for grandparents
                    for other_node in nodes:
                        if other_node['id'] == node['id']:
                            continue
                        for other_contrib in other_node['contributors']:
                            other_rel = other_contrib['relation_to_user'].lower()
                            if 'grandfather' in other_rel or 'grandmother' in other_rel:
                                if contributor['user'] == other_contrib['user']:
                                    edges.append({
                                        'from': other_node['id'],
                                        'to': node['id'],
                                        'type': 'parent-child'
                                    })
        
        return edges
    
    def save_merged_tree(self, name, created_by):
        """Save the merged tree as a MergedFamilyTree"""
        tree = MergedFamilyTree.objects.create(
            name=name,
            created_by=created_by
        )
        tree.members.set(self.users)
        return tree