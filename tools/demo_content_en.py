"""English fixtures for the offline Thunderbird interface tests."""

IDENTITY = "test.user@example.test"
SUBJECTS = (
    "Team meeting — Friday at 10:30 AM",
    "Project Atlas: proposed layout changes",
    "Invoice INV/2026/1106 — documents for review",
    "Travel booking: confirmation and itinerary",
    "Weekly report: results and next steps",
    "Workshop photos — materials for participants",
    "Action required: approve the design before the presentation",
    "November newsletter — product updates",
    "Quick update",
    "Typography check — accents, punctuation and café reservations",
    "A deliberately long message subject to check truncation in a narrow message list and a smaller application window",
    "Order #4821 — delivery date changed",
    "Invitation to the project workshop",
    "Budget — cost breakdown and summary",
    "Deployment status: ready for review",
    "Plans for next week",
)
SENDERS = (
    ("Anna Wilson", "anna.wilson@studio.example.test"),
    ("Michael Cooper", "michael.cooper@atlas.example.test"),
    ("Natalie Taylor", "natalie@office.example.test"),
    ("Peter Johnson", "peter.johnson@projects.example.test"),
    ("Julia Brooks", "julia@workshops.example.test"),
    ("Accounts Team", "invoices@finance.example.test"),
    ("Studio Newsletter", "updates@studio.example.test"),
)
FOLDERS = {
    "Inbox": 32, "Sent": 8, "Drafts": 3, "Templates": 2,
    "Archives": 6, "Trash": 4, "Junk": 3,
    "Projects": 0, "Projects.sbd/Atlas": 8, "Invoices": 6,
}
TABLE = (
    "<tr><th>Item</th><th>Status</th><th>Amount</th></tr>"
    "<tr><td>Interface design</td><td>Awaiting approval</td><td>$1,250.00</td></tr>"
    "<tr><td>Workshop</td><td>Complete</td><td>$480.00</td></tr></table>"
    "<p><strong>Bold text</strong>, <em>italics</em> and "
    "<a href='https://project.example.test'>a sample link</a>.</p>"
)


def body(subject, sender, topic, reply):
    text = (
        f"Hello,\n\n{subject}\n\n"
        "This is a sample message for testing the Thunderbird interface. "
        "You can open it, tag it, move it to a folder or delete it.\n\n"
        "Discussion points:\n1. Pane layout and text readability.\n"
        "2. Message selection and menu behaviour.\n"
        "3. Attachments and the reply window.\n\n"
        "Details: https://project.example.test/preview\n\n"
        f"Best regards,\n{sender}\n"
    )
    if topic == 8:
        text = "Hello, the meeting time is confirmed. Have a great day!\n"
    if topic == 10:
        text += "\n" + "A longer sample paragraph to check how text wraps in the message pane. " * 18
    if reply:
        text += "\nOn the previous day, the team wrote:\n> Please confirm the meeting time.\n> Thank you!\n"
    return text
