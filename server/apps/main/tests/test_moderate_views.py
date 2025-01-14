from django.test import TestCase, Client, RequestFactory
from openhumans.models import OpenHumansMember
from server.apps.main.models import PublicExperience
from django.contrib.auth.models import Group

from server.apps.main.views import moderate_public_experiences
import vcr
import json


class ModerationViewTests(TestCase):
    """
    Test that all moderation views work as expected
    Also account for cases that should fail, e.g. 
    non-logged in users
    """

    def setUp(self):
        '''
        shared user setup for all moderation tests. 
        requires at least 2 users (moderator, regular user)
        '''
        # shared token data for all test users
        data = {"access_token": 'foo',
        "refresh_token": 'bar',
        "expires_in": 36000}
        # create non-moderator OH object
        self.non_moderator_ohmember = OpenHumansMember.create(oh_id="12345678",data=data)
        self.non_moderator_ohmember.save()
        # set password for login with Client()
        self.non_moderator_user = self.non_moderator_ohmember.user
        self.non_moderator_user.openhumansmember = self.non_moderator_ohmember
        self.non_moderator_user.set_password('testpassword')
        self.non_moderator_user.save()
        # create moderator OH object
        self.moderator_oh_user = OpenHumansMember.create(oh_id="23456789",data=data)
        self.moderator_oh_user.save()
        # set password for login with Client()
        self.moderator_user = self.moderator_oh_user.user
        self.moderator_user.set_password('testpassword')
        # create moderator group
        self.moderator_group = Group.objects.create(name='Moderators')
        self.moderator_group.user_set.add(self.moderator_user)
        self.moderator_user.save()
        # create public expierence that needs review
        pe_data = {
            'experience_text': "test",
            'title_text': "title",
            'open_humans_member': self.non_moderator_ohmember,
            'experience_id': 'test-test-test'
        }
        self.pe_object = PublicExperience.objects.create(**pe_data)

    # test moderation pages as logged-out user

    def test_view_moderate_list_logged_out(self):
        """
        Test moderate overview page is not accessible by logged-out users
        """
        c = Client()
        response = c.get("/main/moderate_public_experiences", follow=True)
        self.assertRedirects(response, "/", 
                             status_code=302,target_status_code=200)
        self.assertTemplateUsed(response, 'main/home.html')

    def test_single_moderation_view_as_guest_get(self):
        """
        Test moderate single experience page isn't accessible to logged-out users
        """
        c = Client()
        response = c.get("/main/moderate/test-test-test/", follow=True)
        self.assertRedirects(response, "/",
                             status_code=302, target_status_code=200)
        self.assertTemplateUsed(response, 'main/home.html')

    def test_single_moderation_view_as_guest_post(self):
        """
        Test moderating single experience page fails when done by non-autenticated user
        """
        
        c = Client()        
        response = c.post("/main/moderate/test-test-test/",
                        {"mentalhealth": True, "other":"New trigger",
                        "moderation_status":"approved",
                        "moderation_comments":"amazing story!",
                        },
                        follow=True)
        # assert ending up on right page
        self.assertRedirects(response, "/",
                             status_code=302, target_status_code=200)
        self.assertTemplateUsed(response, 'main/home.html')
        # test that no changes were made
        pe = PublicExperience.objects.get(experience_id='test-test-test')
        self.assertEqual(pe.mentalhealth,False)
        self.assertEqual(pe.other,"")
        self.assertEqual(pe.moderation_status,"not reviewed")

    # test moderation pages as logged-in but non-moderator user

    def test_view_moderate_list_non_moderator(self):
        """
        Test moderate overview page is not accessible by non-moderator users
        """
        c = Client()
        c.force_login(self.non_moderator_user)
        response = c.get("/main/moderate_public_experiences", follow=True)
        self.assertRedirects(response, "/main/overview", 
                             status_code=302,target_status_code=200)
        self.assertTemplateUsed(response, 'main/home.html')

    def test_single_moderation_view_as_non_moderator_get(self):
        """
        Test moderate single experience page isn't accessible by non-moderators
        """
        c = Client()
        c.force_login(self.non_moderator_user)
        response = c.get("/main/moderate/test-test-test/", follow=True)
        self.assertRedirects(response, "/main/overview",
                             status_code=302, target_status_code=200)
        self.assertTemplateUsed(response, 'main/home.html')

    def test_single_moderation_view_as_non_moderator_post(self):
        """
        Test moderating single experience page fails when done by non-moderator
        """
        
        c = Client()
        c.force_login(self.non_moderator_user)
        
        response = c.post("/main/moderate/test-test-test/",
                        {"mentalhealth": True, "other":"New trigger",
                        "moderation_status":"approved",
                        "moderation_comments":"amazing story!",
                        },
                        follow=True)
        # assert ending up on right page
        self.assertRedirects(response, "/main/overview",
                             status_code=302, target_status_code=200)
        self.assertTemplateUsed(response, 'main/home.html')
        # test that no changes were made
        pe = PublicExperience.objects.get(experience_id='test-test-test')
        self.assertEqual(pe.mentalhealth,False)
        self.assertEqual(pe.other,"")
        self.assertEqual(pe.moderation_status,"not reviewed")

    # test moderation pages as logged-in moderator

    def test_view_moderate_list_moderator(self):
        """
        Test moderate overview page is accessible by moderators
        """
        c = Client()
        c.force_login(self.moderator_user)
        response = c.get("/main/moderate_public_experiences", follow=True)
        self.assertEqual(response.status_code,200)
        self.assertTemplateUsed(response, 'main/moderate_public_experiences.html')

    def test_single_moderation_view_as_moderator_get(self):
        """
        Test moderate single experience page is accessible by moderators
        """
        c = Client()
        c.force_login(self.moderator_user)
        response = c.get("/main/moderate/test-test-test/", follow=True)
        self.assertEqual(response.status_code,200)
        self.assertTemplateUsed(response, 'main/moderate_experience.html')


    def test_single_moderation_view_as_moderator_post_missing_data(self):
        """
        Test moderate single experience page is accessible by moderators but access has been revoked
        """
        c = Client()
        c.force_login(self.moderator_user)
        self.assertEqual(len(PublicExperience.objects.all()),1)
        # ideally would add a cassette here too which returns a "permission denied"
        response = c.post("/main/moderate/test-test-test/",
                          {"mentalhealth": True, "other":"New trigger",
                           },
                          follow=True)
        self.assertEqual(response.status_code,200)
        self.assertTemplateUsed(response, 'main/moderate_public_experiences.html')
        # Public experience should be deleted as no longer access on OH
        self.assertEqual(len(PublicExperience.objects.all()),0)

    def test_single_moderation_view_as_moderator_post(self):
        """
        Test moderate single experience page is successfully accessible and editable by moderators
        """
        
        c = Client()
        c.force_login(self.moderator_user)
        # Test uses cassette to allow fake-upload to OH
        with vcr.use_cassette('server/apps/main/tests/fixtures/moderate_experience.yaml',
                      filter_query_parameters=['access_token'],match_on=['path']):
            response = c.post("/main/moderate/test-test-test/",
                            {"mentalhealth": True, "other":"New trigger",
                            "moderation_status":"approved",
                            "moderation_comments":"amazing story!",
                            },
                            follow=True)
        # assert ending up on right page
        self.assertEqual(response.status_code,200)
        self.assertTemplateUsed(response, 'main/moderate_public_experiences.html')
        # test that all changes were made
        pe = PublicExperience.objects.get(experience_id='test-test-test')
        self.assertEqual(pe.mentalhealth,True)
        self.assertEqual(pe.other,"New trigger")
        self.assertEqual(pe.moderation_status,"approved")
        # Try injecting additional information that should be immutable 
        # Should raise KeyError in form
        with self.assertRaises(KeyError) as ce:
            response = c.post("/main/moderate/test-test-test/",
                            {"mentalhealth": True, "other":"New trigger",
                            "moderation_status":"approved",
                            "moderation_comments":"amazing story!",
                            "title_text": 'try injection!'
                            },
                            follow=True)
        # Check that key-error was caused by title text
        self.assertEqual(str(ce.exception),"'title_text'")
            