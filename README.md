# the travelynx relay bot

a bot for [discord](https://en.wikipedia.org/wiki/Apple_of_Discord) and [travelynx](https://travelynx.de), combining the privacy nightmare powers of both to broadcast your live location to your friends and enemies on aforementioned chat programme.

see [this page](/icons/descriptions.md) for a list of all currently supported train types (it won't break on others, it just looks fancier if the train is supported)

to set up a dev environment or host it yourself:
1. install [nix](https://nixos.org/download#download-nix)
2. clone the source code
3. copy `settings.json.example` to `settings.json` and edit to your liking
4. initialize the database: run `sqlite3 travelynx-relay.sqlite3` and copy the outputs of `cat migrations/*` into the sql shell
5. add your server's and optionally a live feed channel's ids to the database (the bot only works with manually added servers for now): `INSERT INTO servers(server_id, live_channel) VALUES(1234,5678);`
6. run `nix-shell` for your dev environment, in there you can start the bot using `python3 -m travelhook`

when developing please occasionally run `black` and maybe even `pylint`. that would be dope

note: if you want to properly set this bot up you will need to add a whole bunch of train type icons as emoji to servers your bot is on and accordingly edit the source code with its ids because your bot won't have access to the servers my bot's emoji are on. i know this is very annoying. sorry
