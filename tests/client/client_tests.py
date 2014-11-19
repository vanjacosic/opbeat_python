# -*- coding: utf-8 -*-

import time

import mock
import opbeat
from opbeat.utils import six
from opbeat.utils.compat import TestCase
from opbeat.base import Client, ClientState
from tests.helpers import get_tempstoreclient


class ClientStateTest(TestCase):
    def test_should_try_online(self):
        state = ClientState()
        self.assertEquals(state.should_try(), True)

    def test_should_try_new_error(self):
        state = ClientState()
        state.status = state.ERROR
        state.last_check = time.time()
        state.retry_number = 1
        self.assertEquals(state.should_try(), False)

    def test_should_try_time_passed_error(self):
        state = ClientState()
        state.status = state.ERROR
        state.last_check = time.time() - 10
        state.retry_number = 1
        self.assertEquals(state.should_try(), True)

    def test_set_fail(self):
        state = ClientState()
        state.set_fail()
        self.assertEquals(state.status, state.ERROR)
        self.assertNotEquals(state.last_check, None)
        self.assertEquals(state.retry_number, 1)

    def test_set_success(self):
        state = ClientState()
        state.status = state.ERROR
        state.last_check = 'foo'
        state.retry_number = 0
        state.set_success()
        self.assertEquals(state.status, state.ONLINE)
        self.assertEquals(state.last_check, None)
        self.assertEquals(state.retry_number, 0)


class ClientTest(TestCase):
    def setUp(self):
        self.client = get_tempstoreclient()

    @mock.patch('opbeat.base.Client._send_remote')
    @mock.patch('opbeat.base.ClientState.should_try')
    def test_send_remote_failover(self, should_try, send_remote):
        should_try.return_value = True

        client = Client(
            servers=['http://example.com'],
            organization_id='organization_id',
            app_id='app_id',
            secret_token='secret',
        )

        # test error
        send_remote.side_effect = Exception()
        client.send_remote('http://example.com/api/store', 'foo')
        self.assertEquals(client.state.status, client.state.ERROR)

        # test recovery
        send_remote.side_effect = None
        client.send_remote('http://example.com/api/store', 'foo')
        self.assertEquals(client.state.status, client.state.ONLINE)

    @mock.patch('opbeat.base.Client.send_remote')
    @mock.patch('opbeat.base.time.time')
    def test_send(self, time, send_remote):
        time.return_value = 1328055286.51
        public = "public"
        access_token = "secret"
        client = Client(
            servers=['http://example.com'],
            organization_id='organization_id',
            app_id='app_id',
            secret_token='secret',
        )
        client.send(**{
            'foo': 'bar',
        })
        send_remote.assert_called_once_with(
            url='http://example.com',
            data=six.b('x\x9c\xabVJ\xcb\xcfW\xb2RPJJ,R\xaa\x05\x00 \x98\x04T'),
            headers={
                'Content-Type': 'application/octet-stream',
                'Authorization': 'Bearer %s' % (access_token),
                'User-Agent': 'opbeat/%s' % opbeat.VERSION
            },
        )

    @mock.patch('opbeat.base.Client.send_remote')
    @mock.patch('opbeat.base.time.time')
    def test_send_with_auth_header(self, time, send_remote):
        time.return_value = 1328055286.51
        client = Client(
            servers=['http://example.com'],
            organization_id='organization_id',
            app_id='app_id',
            secret_token='secret',
        )
        client.send(auth_header='foo', **{
            'foo': 'bar',
        })
        send_remote.assert_called_once_with(
            url='http://example.com',
            data=six.b('x\x9c\xabVJ\xcb\xcfW\xb2RPJJ,R\xaa\x05\x00 \x98\x04T'),
            headers={
                'Content-Type': 'application/octet-stream',
                'Authorization': 'foo',
                'User-Agent': 'opbeat/%s' % opbeat.VERSION

            },
        )

    def test_encode_decode(self):
        data = {'foo': 'bar'}
        encoded = self.client.encode(data)
        self.assertTrue(type(encoded), str)
        self.assertEquals(data, self.client.decode(encoded))

    def test_explicit_message_on_message_event(self):
        self.client.capture('Message', message='test', data={
            'message': 'foo'
        })

        self.assertEquals(len(self.client.events), 1)
        event = self.client.events.pop(0)
        self.assertEquals(event['message'], 'foo')

    def test_explicit_message_on_exception_event(self):
        try:
            raise ValueError('foo')
        except:
            self.client.capture('Exception', data={'message': 'foobar'})

        self.assertEquals(len(self.client.events), 1)
        event = self.client.events.pop(0)
        self.assertEquals(event['message'], 'foobar')

    def test_exception_event(self):
        try:
            raise ValueError('foo')
        except:
            self.client.capture('Exception')

        self.assertEquals(len(self.client.events), 1)
        event = self.client.events.pop(0)
        self.assertEquals(event['message'], 'ValueError: foo')
        self.assertTrue('exception' in event)
        exc = event['exception']
        self.assertEquals(exc['type'], 'ValueError')
        self.assertEquals(exc['value'], 'foo')
        self.assertEquals(exc['module'], ValueError.__module__)  # this differs in some Python versions
        self.assertTrue('stacktrace' in event)
        frames = event['stacktrace']
        self.assertEquals(len(frames['frames']), 1)
        frame = frames['frames'][0]
        self.assertEquals(frame['abs_path'], __file__.replace('.pyc', '.py'))
        self.assertEquals(frame['filename'], 'tests/client/client_tests.py')
        self.assertEquals(frame['module'], __name__)
        self.assertEquals(frame['function'], 'test_exception_event')
        self.assertTrue('timestamp' in event)

    def test_message_event(self):
        self.client.capture('Message', message='test')

        self.assertEquals(len(self.client.events), 1)
        event = self.client.events.pop(0)
        self.assertEquals(event['message'], 'test')
        self.assertFalse('stacktrace' in event)
        self.assertTrue('timestamp' in event)

    def test_logger(self):
        self.client.capture('Message', message='test', data={'logger': 'test'})

        self.assertEquals(len(self.client.events), 1)
        event = self.client.events.pop(0)
        self.assertEquals(event['logger'], 'test')
        self.assertTrue('timestamp' in event)

    def test_long_message(self):
        message = 'm' * 201

        self.client.capture('Message', message=message)

        self.assertEquals(len(self.client.events), 1)
        event = self.client.events.pop(0)
        self.assertTrue(len(event['message']) < 201, len(event['message']))

    def test_long_culprit(self):
        culprit = 'c' * 101

        self.client.capture('Message', message='test', data={'culprit':culprit})

        self.assertEquals(len(self.client.events), 1)
        event = self.client.events.pop(0)
        self.assertTrue(len(event['culprit']) < 101, len(event['culprit']))

    def test_long_logger(self):
        logger = 'c' * 61

        self.client.capture('Message', message='test', data={'logger':logger})

        self.assertEquals(len(self.client.events), 1)
        event = self.client.events.pop(0)
        self.assertTrue(len(event['logger']) < 61, len(event['logger']))
