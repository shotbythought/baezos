# Copyright 2016 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# [START app]
import logging

from flask import Flask, jsonify, request
import flask_cors
from google.appengine.ext import ndb
import google.auth.transport.requests
import google.oauth2.id_token
import requests_toolbelt.adapters.appengine

# Use the App Engine Requests adapter. This makes sure that Requests uses
# URLFetch.
requests_toolbelt.adapters.appengine.monkeypatch()
HTTP_REQUEST = google.auth.transport.requests.Request()

app = Flask(__name__)
flask_cors.CORS(app)


# [START note]
class Note(ndb.Model):
    """NDB model class for a user's note.

    Key is user id from decrypted token.
    """
    friendly_id = ndb.StringProperty()
    message = ndb.TextProperty()
    created = ndb.DateTimeProperty(auto_now_add=True)
# [END note]

class PartnerRequest(ndb.Model):
    """NDB model class for a partner request."""
    asker = ndb.StringProperty()
    receiver = ndb.StringProperty()
    created = ndb.DateTimeProperty(auto_now_add=True)

class Relationship(ndb.Model):
    """NDB model class for a relationship."""
    partner1 = ndb.StringProperty()
    partner2 = ndb.StringProperty()
    created = ndb.DateTimeProperty(auto_now_add=True)

class User(ndb.Model):
    """NDB model class for a user."""
    name = ndb.StringProperty()
    email = ndb.StringProperty()
    uid = ndb.StringProperty()
    created = ndb.DateTimeProperty(auto_now_add=True)


# [START query_database]
def query_database(user_id):
    """Fetches all notes associated with user_id.

    Notes are ordered them by date created, with most recent note added
    first.
    """
    ancestor_key = ndb.Key(Note, user_id)
    query = Note.query(ancestor=ancestor_key).order(-Note.created)
    notes = query.fetch()

    note_messages = []

    for note in notes:
        note_messages.append({
            'friendly_id': note.friendly_id,
            'message': note.message,
            'created': note.created
        })

    return note_messages
# [END query_database]

@app.route('/users', methods=['POST', 'PUT'])
def add_user():
    """Adds a user"""
    id_token = request.headers['Authorization'].split(' ').pop()
    claims = google.oauth2.id_token.verify_firebase_token(id_token, HTTP_REQUEST)

    if not claims:
        return 'Unauthorized', 401

    user = User.query(User.uid == claims['sub']).get()

    if not user:
        new_user = User(name=claims['name'], email=claims['email'], uid=claims['sub'])
        new_user.put()

    return 'Added user', 200



@app.route('/partners', methods=['GET'])
def get_partner():
    """Gets someone's partner"""
    id_token = request.headers['Authorization'].split(' ').pop()
    claims = google.oauth2.id_token.verify_firebase_token(id_token, HTTP_REQUEST)

    if not claims:
        return 'Unauthorized', 401

    query = Relationship.query(ndb.OR(Relationship.partner1 == claims['email'],
                                      Relationship.partner2 == claims['email']))

    relationship = query.get()

    if not relationship:
        return "", 200

    partner_email = relationship.partner1 if relationship.partner1 != claims['email'] else relationship.partner2
    partner = User.query(User.email == partner_email).get()

    return jsonify({
        'email': partner.email,
        'name': partner.name,
        'uid': partner.uid
        })


@app.route('/partners', methods=['POST', 'PUT'])
def request_partner():
    """Registers a partner and adds a request into the database"""
    id_token = request.headers['Authorization'].split(' ').pop()
    claims = google.oauth2.id_token.verify_firebase_token(id_token, HTTP_REQUEST)

    if not claims:
        return 'Unauthorized', 401

    email = request.get_json()['partner']

    user = User.query(User.email == email).get()

    if user is None:
        return 'Nonexistent partner', 428

    partner_request = PartnerRequest(asker=claims['email'], receiver=email)
    partner_request.put()

    query = PartnerRequest.query(PartnerRequest.asker == email, PartnerRequest.receiver == claims['email'])

    if query.get() != None:
        partners = sorted([email, claims['email']])
        relationship = Relationship(partner1=partners[0], partner2=partners[1])

        relationship.put()

    return 'OK', 200

# [START list_notes]
@app.route('/notes', methods=['GET'])
def list_notes():
    """Returns a list of notes added by the current Firebase user."""

    # Verify Firebase auth.
    # [START verify_token]
    id_token = request.headers['Authorization'].split(' ').pop()
    claims = google.oauth2.id_token.verify_firebase_token(
        id_token, HTTP_REQUEST)
    if not claims:
        return 'Unauthorized', 401
    # [END verify_token]

    notes = query_database(claims['sub'])

    return jsonify(notes)
# [END list_notes]


# [START add_note]
@app.route('/notes', methods=['POST', 'PUT'])
def add_note():
    """
    Adds a note to the user's notebook. The request should be in this format:

        {
            "message": "note message."
        }
    """

    # Verify Firebase auth.
    id_token = request.headers['Authorization'].split(' ').pop()
    claims = google.oauth2.id_token.verify_firebase_token(
        id_token, HTTP_REQUEST)
    if not claims:
        return 'Unauthorized', 401

    # [START create_entity]
    data = request.get_json()

    # Populates note properties according to the model,
    # with the user ID as the key name.
    note = Note(
        parent=ndb.Key(Note, claims['sub']),
        message=data['message'])

    # Some providers do not provide one of these so either can be used.
    note.friendly_id = claims.get('name', claims.get('email', 'Unknown'))
    # [END create_entity]

    # Stores note in database.
    note.put()

    return 'OK', 200
# [END add_note]


@app.errorhandler(500)
def server_error(e):
    # Log the error and stacktrace.
    logging.exception('An error occurred during a request.')
    return 'An internal error occurred.', 500
# [END app]
