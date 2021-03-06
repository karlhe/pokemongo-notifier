import json
from geopy.geocoders import Nominatim
from geopy.distance import vincenty
from datetime import datetime
import requests

class Notifier:

	def __init__(self, origin, debug):
		self.debug = debug

		with open('config.json') as data_file:
			data = json.load(data_file)

		# get slack details
		self.slack_key = self.str(data["slack_key"])
		self.slack_channel = self.str(data["slack_channel"])

		if data["notify_ignore"]:
			self.notify_ignore = set([pokemon.lower().strip() for pokemon in data["notify_ignore"].split(',')])

		if data["notify_far_ignore"]:
			self.notify_far_ignore = set([pokemon.lower().strip() for pokemon in data["notify_far_ignore"].split(',')])

		if data["notify_distance"]:
			self.notify_distance = int(data["notify_distance"])

		if data["notify_schedule"]:
			self.notify_schedule = True
			if data["notify_schedule"]["weekdays"]:
				self.notify_weekdays = set([int(day) for day in data["notify_schedule"]["weekdays"]])
			if data["notify_schedule"]["hours"]:
				self.notify_hours = set([int(hour) for hour in data["notify_schedule"]["hours"]])

		# Set origin point to calculate distance from
		self.origin = origin

	# Safely parse incoming strings to unicode
	@staticmethod
	def str(s):
		return s.encode('utf-8').strip()

	# Approximates distance from origin
	def distance(self, point):
		dist = vincenty(self.origin, point).meters
		self.debug("Distance is {}m.".format(int(dist)))
		return dist

	def within_schedule(self):
		if self.notify_schedule:
			now = datetime.now()
			if self.notify_weekdays and now.weekday() not in self.notify_weekdays:
				self.debug("{} not in scheduled weekdays.".format(now.weekday()))
				return False
			if self.notify_hours and now.hour not in self.notify_hours:
				self.debug("{} not in scheduled hours.".format(now.hour))
				return False

			# Passed all checks
			return True
		else:
			# Scheduling not enabled
			return True

	# Notify user for discovered Pokemon
	def pokemon_found(self, pokemon):
		if not self.within_schedule():
			return

		pokename = self.str(pokemon["name"])
		pokeid = str(pokemon["id"])

		# Mark as "far" if outside distance limit
		coordinates = (pokemon["lat"], pokemon["lng"])
		far = False
		distance = None
		if self.notify_distance:
			distance = self.distance(coordinates)
			if self.distance(coordinates) > self.notify_distance:
				self.debug("Pokemon {} is far away.".format(pokename))
				far = True

		# Don't notify if on ignore list
		if far:
			if self.notify_far_ignore:
				if pokename.lower() in self.notify_far_ignore or pokeid in self.notify_far_ignore:
					self.debug("Ignored {}.".format(pokename))
					return
			else:
				self.debug("Ignored {}.".format(pokename))
				return
		elif self.notify_ignore:
			if pokename.lower() in self.notify_ignore or pokeid in self.notify_ignore:
				self.debug("Ignored {}.".format(pokename))
				return

		# We're good to notify!
		self.debug("Notifying {}:{}.".format(pokeid, pokename))

		# Locate pokemon on GMAPS
		maps_link = "http://maps.google.com/maps?q={},{}&20z".format(str(coordinates[0]), str(coordinates[1]))

		# Get disappearance time
		disappear_time = str(datetime.fromtimestamp(pokemon["disappear_time"]).strftime("%I:%M%p").lstrip('0'))

		# Create notification
		if far:
			notification_text = "*{}* is {}m away until *{}* ({})".format(pokename, int(distance), disappear_time, maps_link)
		else:
			notification_text = "*{}* is nearby until *{}* ({})".format(pokename, disappear_time, maps_link)

		# Post to Slack
		post_url = "https://slack.com/api/chat.postMessage"
		post_params = { "token": self.slack_key, "as_user": "true", "channel": self.slack_channel, "text": notification_text }
		response = requests.post(post_url, data=post_params)
