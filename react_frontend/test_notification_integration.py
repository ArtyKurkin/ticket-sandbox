import json
import re
from django.contrib.auth.models import User
from django.template import RequestContext, Template
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse


@override_settings(DEBUG=True)
class NotificationHostIntegrationTests(TestCase):
    def test_one_shared_host_on_required_pages_and_actual_owner_config(self):
        user=User.objects.create_user('host-owner')
        self.client.force_login(user)
        for name in ['roadmap','achievements','sandbox:dashboard']:
            response=self.client.get(reverse(name))
            self.assertEqual(response.status_code,200)
            self.assertContains(response,'id="achievement-notification-host"',count=1)
            config=json.loads(re.search(r'<script id="achievement-notification-config" type="application/json">(.*?)</script>',response.content.decode(),re.S)[1])
            self.assertEqual(config['userId'],user.pk)
            self.assertEqual(config['feedUrl'],reverse('achievement_api:notifications'))
            self.assertEqual(config['trophyRoomUrl'],reverse('achievements'))
            self.assertTrue(config['csrfToken'])
            self.assertIn('csrftoken',response.cookies)

    def test_duplicate_template_include_does_not_mount_twice_or_anonymously(self):
        template=Template('{% load achievement_notifications %}{% achievement_notification_host %}{% achievement_notification_host %}')
        request=RequestFactory().get('/')
        request.user=User.objects.create_user('host-singleton')
        rendered=template.render(RequestContext(request,{}))
        self.assertEqual(rendered.count('id="achievement-notification-host"'),1)
        from django.contrib.auth.models import AnonymousUser
        request=RequestFactory().get('/');request.user=AnonymousUser()
        self.assertNotIn('notification-host',template.render(RequestContext(request,{})))
