CREATE TABLE users (
	discord_id INTEGER PRIMARY KEY,
	token_status TEXT NOT NULL,
	token_webhook TEXT,
	token_travel TEXT
);

CREATE UNIQUE INDEX idx_token_webhook ON users(token_webhook);

CREATE TABLE privacy (
	user_id INTEGER NOT NULL,
	server_id INTEGER NOT NULL,
	privacy_level INTEGER NOT NULL,
	PRIMARY KEY (user_id, server_id)
);

CREATE TABLE servers (
	server_id INTEGER PRIMARY KEY,
	live_channel INTEGER
);

CREATE TABLE trips (
	journey_id INTEGER NOT NULL,
	user_id INTEGER NOT NULL,
	travelynx_status	 TEXT NOT NULL,
	
	from_time DATE NOT NULL,
	from_station TEXT NOT NULL,
	from_lat FLOAT,
	from_lon FLOAT,
	
	to_time DATE NOT NULL,
	to_station TEXT NOT NULL,
	to_lat FLOAT,
	to_lon FLOAT,
	
	PRIMARY KEY (journey_id, user_id)
);

CREATE TABLE messages (
	journey_id INTEGER NOT NULL,
	user_id INTEGER NOT NULL,
	channel_id INTEGER NOT NULL,
	message_id INTEGER NOT NULL
);
