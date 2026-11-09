"""Check the English MIME fixture, including content beyond the message subject."""
import unittest

from create_test_profiles import message


class EnglishMailTests(unittest.TestCase):
    def test_english_headers_body_html_and_attachments(self):
        mail = message('Inbox', 0, 'en-US')
        self.assertEqual(mail['Subject'], 'Team meeting — Friday at 10:30 AM')
        self.assertIn('Test User <test.user@example.test>', mail['To'])
        self.assertIn('Project Team', mail['Cc'])
        self.assertIn('Discussion points:', mail.get_body(('plain',)).get_content())
        self.assertIn('<th>Amount</th>', mail.get_body(('html',)).get_content())
        attachments = list(mail.iter_attachments())
        self.assertEqual([a.get_filename() for a in attachments],
                         ['november-summary.csv', 'meeting-notes.txt'])
        self.assertIn('Product,Quantity,Price', attachments[0].get_content())
        self.assertIn('Sample meeting notes.', attachments[1].get_content())
        reply = message('Inbox', 16, 'en-US')
        self.assertIn('> Please confirm the meeting time.', reply.get_body(('plain',)).get_content())
        self.assertEqual(reply['In-Reply-To'], '<demo-Inbox-0@example.test>')
        sent = message('Sent', 0, 'en-US')
        self.assertEqual(sent['From'], 'Test User <test.user@example.test>')


if __name__ == '__main__':
    unittest.main()
