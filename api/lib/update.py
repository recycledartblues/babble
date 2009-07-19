#!/usr/bin/env python
from __future__ import absolute_import

import lib.SQL as SQL 
import lib.amalgutils as amalgutils
import lib.const.event as event
import lib.const.config as config
import lib.template as template
import lib.const.event as event
import random
import datetime

def start_new_game(cursor, roomid):
	roundid = amalgutils.get_current_round_id(cursor, roomid)
	amalgutils.add_event(cursor, roundid, event.GAME_OVER)
	cursor.execute('INSERT INTO games (roomid) VALUES (%s)', roomid)

def addpoints(dict, name, points):
	dict[name] = points + dict.get(name, 0)

def game_is_over(cursor, roomid):
	# TODO: benchmark, denormalizing could make this way more efficient probably
	curgameid = amalgutils.get_current_game_id(cursor, roomid)
	cursor.execute('SELECT id FROM rounds WHERE gameid = %s', curgameid)
	rows = cursor.fetchall()
	points = {}
	for row in rows:
		roundid = row['id']
		winner, votes = amalgutils.get_winner_data(cursor, roundid)
		if winner:
			addpoints(points, winner, config.POINTS_FOR_WINNING_ROUND)
		for voter in votes:
			addpoints(points, votes[voter], 1)
			if votes[voter] == winner:
				addpoints(points, voter, config.POINTS_FOR_VOTING_WINNER)
	for username in points:
		if points[username] > config.POINTS_TO_WIN:
			return True
	return False

def round_end(cursor, roomid):
	if game_is_over(cursor, roomid):
		start_new_game(cursor, roomid)
	else:
		start_new_round(cursor, roomid)

def start_new_round(cursor, roomid):
	cursor.execute('SELECT word, minnum, id FROM words')
	rows = cursor.fetchall()
	wordrows = []
	for row in rows:
		for i in range(row["minnum"]):
			wordrows.append(row)

	while len(wordrows) < config.WORDS_PER_ROUND:
		wordrows.append(random.choice(rows))

	# add it to the SQL server
	# this is not actually a race condition - last_insert_id is per-connection
	# note that this will only work unmodified on MySQL
	gameid = amalgutils.get_current_game_id(cursor, roomid)
	cursor.execute('INSERT INTO rounds (gameid) VALUES (%s)', gameid)
	cursor.execute('SELECT LAST_INSERT_ID()')
	row = cursor.fetchone()
	roundid = row['LAST_INSERT_ID()']
	cursor.executemany(
		'INSERT INTO roundwords (roundid, wordid) VALUES (%s, %s)',
		[(roundid, wordrow['id']) for wordrow in wordrows])

	amalgutils.add_event(cursor, roundid, event.ROUND_START)

def update_room(cursor, roomid):
	if not amalgutils.is_valid_room(cursor, roomid):
		return
	gameid = amalgutils.get_current_game_id(cursor, roomid)
	round = amalgutils.get_current_round_data(cursor, roomid)
	if not gameid:
		start_new_game(cursor, roomid)
		return
	if not round:
		start_new_round(cursor, roomid)
		return
	cursor.execute(
		'''SELECT eventtype, value, id, time FROM events WHERE roundid = %s ORDER BY time DESC''',
		round['id'])
	row = cursor.fetchone()
	if row:
		cureventtime = row['time']
		cureventtype = row['eventtype']
		eventtypes = (
			(event.ROUND_START, config.SENTENCE_MAKING_TIME, event.SENTENCE_MAKING_OVER, None),
			(event.SENTENCE_MAKING_OVER, config.SENTENCE_COLLECTING_TIME, event.COLLECTING_OVER, None),
			(event.COLLECTING_OVER, config.VOTING_TIME, event.VOTING_OVER, None),
			(event.VOTING_OVER, config.VOTE_COLLECTING_TIME, event.VOTE_COLLECTING_OVER, None),
			(event.VOTE_COLLECTING_OVER, config.WINNER_VIEWING_TIME, None, round_end),
			(event.GAME_OVER, config.GAME_WINNER_VIEWING_TIME, None, start_new_round))
		for x in eventtypes:
			eventtype, time, nexttype, action = x
			if cureventtype == eventtype:
				delta = datetime.timedelta(seconds = time) 
				if datetime.datetime.today() - cureventtime > delta:
					if nexttype:
						amalgutils.add_event(cursor, round['id'], nexttype) 
					if action:
						action(cursor, roomid)
				break