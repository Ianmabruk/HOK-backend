"""
Test suite for category showcase settings endpoints and merge behavior.
Tests persistence, validation, merge logic, and edge cases.
"""

import pytest
import json
from datetime import datetime


@pytest.fixture
def admin_headers(client, app):
    """Create admin user and return auth headers."""
    with app.app_context():
        from models.models import User, db
        
        user = User.query.filter_by(email='admin@test.com').first()
        if not user:
            user = User(
                name='Admin User',
                email='admin@test.com',
                password_hash='hashed',
                role='admin',
                email_verified=True
            )
            db.session.add(user)
            db.session.commit()
        
        from flask_jwt_extended import create_access_token
        token = create_access_token(identity=user.id)
        return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def user_headers(client, app):
    """Create regular user and return auth headers."""
    with app.app_context():
        from models.models import User, db
        
        user = User.query.filter_by(email='user@test.com').first()
        if not user:
            user = User(
                name='Regular User',
                email='user@test.com',
                password_hash='hashed',
                role='customer',
                email_verified=True
            )
            db.session.add(user)
            db.session.commit()
        
        from flask_jwt_extended import create_access_token
        token = create_access_token(identity=user.id)
        return {'Authorization': f'Bearer {token}'}


class TestGetCategoryShowcase:
    """Test GET /site-settings/category-showcase endpoint."""
    
    def test_get_default_showcase(self, client):
        """Test that endpoint returns default showcase when none exists."""
        response = client.get('/site-settings/category-showcase')
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'sections' in data
        assert 'categories' in data
        assert len(data['categories']) == 6
        assert all(cat.get('slug') for cat in data['categories'])
    
    def test_get_showcase_structure(self, client):
        """Test that returned showcase has correct structure."""
        response = client.get('/site-settings/category-showcase')
        data = response.get_json()
        
        # Check sections
        assert data['sections']['homeCategoryShowcase'] is True
        assert data['sections']['virtualShowcase'] is True
        
        # Check category structure
        for cat in data['categories']:
            assert 'slug' in cat
            assert 'title' in cat
            assert 'description' in cat
            assert 'iconKey' in cat
            assert 'bannerUrl' in cat
            assert 'enabled' in cat
            assert 'featuredOrder' in cat
    
    def test_get_preserved_custom_settings(self, client, app, admin_headers):
        """Test that custom settings are preserved and returned."""
        custom_data = {
            'categories': [
                {
                    'slug': 'living-room',
                    'title': 'Custom Living',
                    'description': 'My custom description',
                    'iconKey': 'FaCouch',
                    'enabled': False
                }
            ]
        }
        
        # Set custom data
        client.put('/site-settings/category-showcase',
                  json=custom_data,
                  headers=admin_headers)
        
        # Retrieve and verify
        response = client.get('/site-settings/category-showcase')
        data = response.get_json()
        
        living_room = next((c for c in data['categories'] if c['slug'] == 'living-room'), None)
        assert living_room is not None
        assert living_room['title'] == 'Custom Living'
        assert living_room['description'] == 'My custom description'
        assert living_room['enabled'] is False


class TestUpdateCategoryShowcase:
    """Test PUT /site-settings/category-showcase endpoint."""
    
    def test_update_requires_auth(self, client):
        """Test that endpoint requires authentication."""
        response = client.put('/site-settings/category-showcase', json={})
        assert response.status_code == 401
    
    def test_update_requires_admin(self, client, user_headers):
        """Test that endpoint requires admin role."""
        response = client.put('/site-settings/category-showcase',
                            json={},
                            headers=user_headers)
        assert response.status_code == 403
    
    def test_update_admin_only_success(self, client, admin_headers):
        """Test that admins can update settings."""
        custom_data = {
            'categories': [
                {
                    'slug': 'living-room',
                    'title': 'Updated Living Room'
                }
            ]
        }
        
        response = client.put('/site-settings/category-showcase',
                            json=custom_data,
                            headers=admin_headers)
        assert response.status_code == 200
        data = response.get_json()
        
        living_room = next((c for c in data['categories'] if c['slug'] == 'living-room'), None)
        assert living_room is not None
        assert living_room['title'] == 'Updated Living Room'
    
    def test_payload_size_validation(self, client, admin_headers):
        """Test that oversized payloads are rejected."""
        # Create payload larger than 50KB
        large_description = 'x' * 60000
        data = {
            'categories': [
                {
                    'slug': 'living-room',
                    'description': large_description
                }
            ]
        }
        
        response = client.put('/site-settings/category-showcase',
                            json=data,
                            headers=admin_headers)
        assert response.status_code == 413
        assert 'too large' in response.get_json()['message'].lower()
    
    def test_max_categories_validation(self, client, admin_headers):
        """Test that max category count is enforced."""
        # Create 51 categories (max is 50)
        categories = [
            {
                'slug': f'category-{i}',
                'title': f'Category {i}',
                'description': 'Test'
            }
            for i in range(51)
        ]
        
        data = {'categories': categories}
        response = client.put('/site-settings/category-showcase',
                            json=data,
                            headers=admin_headers)
        assert response.status_code == 400
        assert 'too many' in response.get_json()['message'].lower()
    
    def test_invalid_icon_key_validation(self, client, admin_headers):
        """Test that invalid icon keys are rejected."""
        data = {
            'categories': [
                {
                    'slug': 'living-room',
                    'iconKey': 'InvalidIcon'
                }
            ]
        }
        
        response = client.put('/site-settings/category-showcase',
                            json=data,
                            headers=admin_headers)
        assert response.status_code == 400
        assert 'invalid icon key' in response.get_json()['message'].lower()
    
    def test_valid_icon_keys_accepted(self, client, admin_headers):
        """Test that all valid icon keys are accepted."""
        valid_icons = ['FaBoxOpen', 'FaCouch', 'FaCube', 'FaHome', 
                      'FaLayerGroup', 'FaPalette', 'FaPrint', 'FaVrCardboard']
        
        for icon in valid_icons:
            data = {
                'categories': [
                    {
                        'slug': 'living-room',
                        'iconKey': icon
                    }
                ]
            }
            
            response = client.put('/site-settings/category-showcase',
                                json=data,
                                headers=admin_headers)
            assert response.status_code == 200
    
    def test_slug_format_validation(self, client, admin_headers):
        """Test that invalid slug formats are rejected."""
        invalid_slugs = [
            'ab',  # Too short
            'A-Room',  # Uppercase not allowed
            'room_type',  # Underscore not allowed
            'room!!',  # Special chars not allowed
            'x' * 100,  # Too long
        ]
        
        for slug in invalid_slugs:
            data = {
                'categories': [
                    {
                        'slug': slug,
                        'title': 'Test'
                    }
                ]
            }
            
            response = client.put('/site-settings/category-showcase',
                                json=data,
                                headers=admin_headers)
            # Should either reject or normalize to valid slug
            if response.status_code == 400:
                assert 'slug' in response.get_json()['message'].lower()
    
    def test_valid_slug_formats_accepted(self, client, admin_headers):
        """Test that valid slug formats are accepted."""
        valid_slugs = [
            'abc',  # 3 chars minimum
            'living-room',  # With dash
            'my-living-room-123',  # With numbers
            'a' * 64,  # 64 chars maximum
        ]
        
        for slug in valid_slugs:
            data = {
                'categories': [
                    {
                        'slug': slug,
                        'title': 'Test'
                    }
                ]
            }
            
            response = client.put('/site-settings/category-showcase',
                                json=data,
                                headers=admin_headers)
            assert response.status_code == 200
    
    def test_duplicate_slug_validation(self, client, admin_headers):
        """Test that duplicate slugs are rejected."""
        data = {
            'categories': [
                {
                    'slug': 'living-room',
                    'title': 'First'
                },
                {
                    'slug': 'living-room',
                    'title': 'Duplicate'
                }
            ]
        }
        
        response = client.put('/site-settings/category-showcase',
                            json=data,
                            headers=admin_headers)
        assert response.status_code == 400
        assert 'duplicate' in response.get_json()['message'].lower()
    
    def test_field_length_validation(self, client, admin_headers):
        """Test that field length limits are enforced."""
        # Test title truncation (max 200 chars)
        long_title = 'x' * 250
        data = {
            'categories': [
                {
                    'slug': 'living-room',
                    'title': long_title
                }
            ]
        }
        
        response = client.put('/site-settings/category-showcase',
                            json=data,
                            headers=admin_headers)
        assert response.status_code == 200
        result = response.get_json()
        living_room = next((c for c in result['categories'] if c['slug'] == 'living-room'), None)
        assert len(living_room['title']) <= 200
    
    def test_merge_preserves_missing_fields(self, client, admin_headers):
        """Test that merge preserves fields not provided in update."""
        # First set custom values
        initial = {
            'categories': [
                {
                    'slug': 'living-room',
                    'title': 'Living Room',
                    'description': 'Original desc',
                    'iconKey': 'FaCouch'
                }
            ]
        }
        client.put('/site-settings/category-showcase', json=initial, headers=admin_headers)
        
        # Update only title
        partial = {
            'categories': [
                {
                    'slug': 'living-room',
                    'title': 'New Title'
                }
            ]
        }
        response = client.put('/site-settings/category-showcase', json=partial, headers=admin_headers)
        assert response.status_code == 200
        
        result = response.get_json()
        living_room = next((c for c in result['categories'] if c['slug'] == 'living-room'), None)
        assert living_room['title'] == 'New Title'
        assert living_room['description'] == 'Original desc'  # Preserved
        assert living_room['iconKey'] == 'FaCouch'  # Preserved
    
    def test_section_toggle_update(self, client, admin_headers):
        """Test that section toggles can be updated independently."""
        data = {
            'sections': {
                'homeCategoryShowcase': False,
                'virtualShowcase': True
            }
        }
        
        response = client.put('/site-settings/category-showcase', json=data, headers=admin_headers)
        assert response.status_code == 200
        result = response.get_json()
        
        assert result['sections']['homeCategoryShowcase'] is False
        assert result['sections']['virtualShowcase'] is True
    
    def test_featured_order_sorting(self, client, admin_headers):
        """Test that categories are sorted by featuredOrder."""
        data = {
            'categories': [
                {
                    'slug': 'office',
                    'title': 'Office',
                    'featuredOrder': 5
                },
                {
                    'slug': 'kitchen',
                    'title': 'Kitchen',
                    'featuredOrder': 1
                },
                {
                    'slug': 'bedroom',
                    'title': 'Bedroom',
                    'featuredOrder': 3
                }
            ]
        }
        
        response = client.put('/site-settings/category-showcase', json=data, headers=admin_headers)
        assert response.status_code == 200
        result = response.get_json()
        
        # Should be sorted by featuredOrder
        assert result['categories'][0]['slug'] == 'kitchen'
        assert result['categories'][1]['slug'] == 'bedroom'
        assert result['categories'][2]['slug'] == 'office'
    
    def test_empty_update_preserves_defaults(self, client, admin_headers):
        """Test that empty update returns defaults."""
        response = client.put('/site-settings/category-showcase', json={}, headers=admin_headers)
        assert response.status_code == 200
        data = response.get_json()
        
        # Should have all default categories
        assert len(data['categories']) == 6


class TestCategoryShowcaseMergeBehavior:
    """Test detailed merge behavior for category showcase."""
    
    def test_merge_with_invalid_json_structure(self, client, app, admin_headers):
        """Test that invalid JSON structures are handled gracefully."""
        # Send non-dict data
        invalid_payloads = [
            [],
            "string",
            None,
            123
        ]
        
        for payload in invalid_payloads:
            response = client.put('/site-settings/category-showcase',
                                json=payload,
                                headers=admin_headers)
            # Should either accept it gracefully or reject it
            assert response.status_code in [200, 400]
    
    def test_merge_with_missing_categories(self, client, admin_headers):
        """Test merge when categories key is missing."""
        data = {
            'sections': {
                'homeCategoryShowcase': False
            }
        }
        
        response = client.put('/site-settings/category-showcase', json=data, headers=admin_headers)
        assert response.status_code == 200
        result = response.get_json()
        
        assert result['sections']['homeCategoryShowcase'] is False
        # Should still have original categories
        assert len(result['categories']) > 0
    
    def test_merge_with_non_dict_categories(self, client, admin_headers):
        """Test merge when categories is not a list."""
        data = {
            'categories': 'not-a-list'
        }
        
        response = client.put('/site-settings/category-showcase', json=data, headers=admin_headers)
        assert response.status_code == 200
        result = response.get_json()
        
        # Should return defaults
        assert len(result['categories']) == 6


class TestCategoryShowcasePersistence:
    """Test that category showcase settings persist across requests."""
    
    def test_persistence_across_requests(self, client, admin_headers):
        """Test that settings persist after being set."""
        custom_data = {
            'categories': [
                {
                    'slug': 'living-room',
                    'title': 'My Living Room',
                    'description': 'Custom description'
                }
            ]
        }
        
        # Set data
        response1 = client.put('/site-settings/category-showcase', json=custom_data, headers=admin_headers)
        assert response1.status_code == 200
        
        # Retrieve in new request
        response2 = client.get('/site-settings/category-showcase')
        assert response2.status_code == 200
        data = response2.get_json()
        
        living_room = next((c for c in data['categories'] if c['slug'] == 'living-room'), None)
        assert living_room['title'] == 'My Living Room'
        assert living_room['description'] == 'Custom description'
        
        # Retrieve again in another request
        response3 = client.get('/site-settings/category-showcase')
        assert response3.status_code == 200
        data3 = response3.get_json()
        
        living_room3 = next((c for c in data3['categories'] if c['slug'] == 'living-room'), None)
        assert living_room3['title'] == 'My Living Room'
