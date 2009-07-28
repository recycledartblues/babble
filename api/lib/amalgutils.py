from __future__ import absolute_import
import lib.template as template
import lib.const.config as config
import lib.const.event as event

def get_current_game_id(cursor, roomid):
	cursor.execute('''SELECT id FROM games
	WHERE roomid = %s ORDER BY id DESC LIMIT 1''', roomid)
	row = cursor.fetchone()
	if not row:
		return None
	else:
		return row['id']

def get_current_round_id(cursor, roomid):
	row = get_current_round_data(cursor, roomid)
	if not row:
		return None
	else:
		return row['id']

def get_current_round_data(cursor, roomid):
	cursor.execute('''
	SELECT rounds.id, rounds.starttime
	FROM rounds JOIN games ON rounds.gameid = games.id
	WHERE games.roomid = %s 
	ORDER BY rounds.id DESC LIMIT 1''', roomid)
	row = cursor.fetchone()
	if not row:
		return None
	else:
		return row

def add_event(cursor, roundid, eventtype, value = None):
	cursor.execute('INSERT INTO events (roundid, eventtype, value) VALUES (%s, %s, %s)',
		(roundid, eventtype, value))

def is_valid_room(cursor, roomid):
	if not roomid:
		return False
	cursor.execute('SELECT id FROM rooms WHERE id = %s', roomid)
	if cursor.fetchone():
		return True
	return False

def get_winner_data(cursor, roundid):
	cursor.execute('''
	SELECT voters.username AS votername, votees.username AS voteename
	FROM roommembers JOIN votes ON roommembers.userid = votes.userid
	JOIN users voters ON votes.userid = voters.id
	JOIN users votees ON votes.voteid = votees.id
	WHERE votes.roundid = %s ORDER BY votes.id''', roundid)
	rows = cursor.fetchall()
	votes = {}
	votecounts = {}
	mostvotes = 0
	winner = None
	# TODO: a better winning algorithm than "whoever was first to get more 
	# votes than everyone else"
	# TODO: make it work with the people who got no votes too
	# TODO: make it return the sentences too
	for row in rows:
		voter = row['votername']
		votee = row['voteename']
		votes[voter] = votee
	
	for voter in votes:
		votee = votes[voter]
		if votee in votes:
			if votee in votecounts:
				votecounts[votee] += 1
			else:
				votecounts[votee] = 1
			if votecounts[votee] > mostvotes:
				mostvotes = votecounts[votee]
				winner = votee
	
	# got the votes, now get the sentences
	cursor.execute('''
	SELECT words.word AS word, sentences.id AS id, users.username as username
	FROM roommembers JOIN sentences ON roommembers.userid = sentences.userid
	JOIN rounds ON sentences.roundid = rounds.id
	JOIN users ON roommembers.userid = users.id
	JOIN words ON sentences.wordid = words.id
	WHERE rounds.id = %s ORDER BY sentences.id''', roundid)

	sentences_by_user = {}
	rows = cursor.fetchall()
	for row in rows:
		if row['username'] in sentences_by_user:
			sentences_by_user[row['username']].append(row['word'])
		else:
			sentences_by_user[row['username']] = [row['word']]
	
	data = {}
	for username in sentences_by_user:
		dat = {}
		dat['sentence'] = sentences_by_user[username]
		
		if username in votecounts:
			dat['votes'] = votecounts[username]
		else:
			dat['votes'] = 0
		
		if username in votes:
			dat['vote'] = votes[username]
			score = dat['votes']
			if winner == username:
				score += config.POINTS_FOR_WINNING_ROUND
			if dat['vote'] == winner:
				score += config.POINTS_FOR_VOTING_WINNER
			dat['score'] = score
		else:
			dat['vote'] = None
			dat['score'] = 0
		
		if username == winner:
			dat['iswinner'] = True
		else:
			dat['iswinner'] = False
		
		data[username] = dat

	# Note that currently usernames can only be alphanumeric + _, so there's no
	# need to sanitize, either here or clientside.
	return data

def get_scores(cursor, roomid):
	# TODO: benchmark, denormalizing could make this way more efficient probably
	cursor.execute('''SELECT users.username AS username
	FROM roommembers JOIN users ON roommembers.userid = users.id
	WHERE roommembers.roomid = %s''', roomid)
	rows = cursor.fetchall()
	points = {}
	for row in rows:
		points[row['username']] = 0
			
	curgameid = get_current_game_id(cursor, roomid)
	cursor.execute('SELECT id FROM rounds WHERE gameid = %s', curgameid)
	rows = cursor.fetchall()
	for row in rows:
		roundid = row['id']
		data = get_winner_data(cursor, roundid)
		for username in data:
			if username in points:
				points[username] = data[username]['score']
	return points

def username_from_userid(cursor, userid):
	cursor.execute('SELECT username FROM users WHERE id = %s', userid)
	row = cursor.fetchone()
	if row:
		return row['username']
	else:
		return None

def get_room_member_names(cursor, roomid):
	cursor.execute('''SELECT users.username AS username
		FROM users JOIN roommembers ON users.id = roommembers.userid
		WHERE roommembers.roomid = %s''', roomid)
	rows = cursor.fetchall()
	names = []
	for row in rows:
		names.append(row['username'])
	return names

def chatmessage_from_id(cursor, id):
	cursor.execute('''SELECT users.username AS username, chatmessages.text AS text
		FROM chatmessages JOIN users ON users.id = chatmessages.userid
		WHERE chatmessages.id = %s''', id)
	return cursor.fetchone()

def get_current_state(cursor, roundid):
	cursor.execute(
		'SELECT eventtype FROM events WHERE roundid = %s AND eventtype <= %s ORDER BY id DESC',
		(roundid, event.GAME_OVER))
	row = cursor.fetchone()
	if row:
		return row['eventtype']
	else:
		return None
