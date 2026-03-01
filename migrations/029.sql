drop table cts_stops;
CREATE TABLE cts_stops(
	name TEXT,
	translated TEXT
);

-- generated with
-- curl -X 'GET' 'https://api.cts-strasbourg.eu/v1/siri/2.0/stoppoints-discovery' -H 'accept: text/plain' -H "Authorization: Basic [the token and a trailing colon base64 encoded]" | jq -r '.StopPointsDelivery.AnnotatedStopPointRef[]|"insert or replace into cts_stops values(\'\\(.StopName|sub("\'"; "\'\'"))\', \'\');"' | sort | uniq
-- regenerate as needed (rarely probably)

insert or replace into cts_stops values('Parc des Sports Zénith', 'Sportpark/Zénith');
insert or replace into cts_stops values('Le Galet', 'Stein');
insert or replace into cts_stops values('Cervantes', 'Cervantesstraße');
insert or replace into cts_stops values('Dante', 'Dantestraße');
insert or replace into cts_stops values('Hôpital de Hautepierre', 'Hohensteiner Krankenhaus');
insert or replace into cts_stops values('Ducs d''Alsace', 'Herzogstraße');
insert or replace into cts_stops values('Saint Florent', 'St. Florentius');
insert or replace into cts_stops values('Rotonde', 'Rotunde');
insert or replace into cts_stops values('Gare Centrale', 'Hauptbahnhof');
insert or replace into cts_stops values('Ancienne Synagogue / Les Halles', 'Alte Synagoge/Einkaufszentrum');
insert or replace into cts_stops values('Homme de Fer', 'Eisenmannplatz');
insert or replace into cts_stops values('Langstross/Grand Rue', 'Lange Straße');
insert or replace into cts_stops values('Porte de l''Hôpital', 'Spitalstor');
insert or replace into cts_stops values('Etoile Bourse', 'Börse am Sternpark');
insert or replace into cts_stops values('Schluthfeld', 'Schluthfeldplatz');
insert or replace into cts_stops values('Krimmeri Stade de la Meinau', 'Krimmeriplatz/Meinaustadion');
insert or replace into cts_stops values('Lycée Couffignal', 'Louis-Couffignal-Gymnasium');
insert or replace into cts_stops values('Emile Mathis', 'Emile-Mathis-Straße');
insert or replace into cts_stops values('Hohwart', 'Hohwartstraße');
insert or replace into cts_stops values('Baggersee', 'Baggersee');
insert or replace into cts_stops values('Colonne', 'Kolonnenweg');
insert or replace into cts_stops values('Leclerc', 'Leclerckaserne');
insert or replace into cts_stops values('Campus d''Illkirch', 'Illkirch Campus');
insert or replace into cts_stops values('Illkirch Lixenbuhl', 'Illkirch Lixenbühlstraße');
insert or replace into cts_stops values('Parc Malraux', 'Malrauxpark');
insert or replace into cts_stops values('Cours de l''Illiade', 'Iliasweg');
insert or replace into cts_stops values('Graffenstaden', 'Graffenstaden');

insert or replace into cts_stops values('Lingolsheim Tiergaertel', 'Lingolsheim Tiergärtelstraße');
insert or replace into cts_stops values('Lingolsheim Alouettes', 'Lingolsheim Lerchenstraße');
insert or replace into cts_stops values('Bohrie', 'Bohrieallee');
insert or replace into cts_stops values('Ostwald Hôtel de Ville', 'Ostwald Rathaus');
insert or replace into cts_stops values('Wihrel', 'Wihrel');
insert or replace into cts_stops values('Elmerforst', 'Elmerforststraße');
insert or replace into cts_stops values('Martin Schongauer', 'Martin-Schongauer-Straße');
insert or replace into cts_stops values('Elsau', 'Elsau');
insert or replace into cts_stops values('Montagne Verte', 'Grünbergstraße');
insert or replace into cts_stops values('Laiterie', 'Molkerei');
insert or replace into cts_stops values('Musée d''Art Moderne', 'Museum der modernen Kunst');
insert or replace into cts_stops values('Faubourg National Gare Centrale', 'Nationalvorstadt/Hauptbahnhof');
insert or replace into cts_stops values('Alt Winmärik-Vieux Marché aux Vins', 'Alter Weinmarkt');
insert or replace into cts_stops values('Broglie', 'Broglieplatz');
insert or replace into cts_stops values('République', 'Platz der Republik');
insert or replace into cts_stops values('Parc du Contades', 'Contades-Park');
insert or replace into cts_stops values('Lycée Kléber', 'Klébergymnasium');
insert or replace into cts_stops values('Wacken', 'Wacken');
insert or replace into cts_stops values('Rives de l''Aar', 'Aarufer');
insert or replace into cts_stops values('Futura Glaciere', 'Eisfabrikstraße');
insert or replace into cts_stops values('Le Marais', 'Marais');
insert or replace into cts_stops values('Pont Phario', 'Phariobrücke');
insert or replace into cts_stops values('Lycée Marc Bloch', 'Marc-Bloch-Gymnasium');
insert or replace into cts_stops values('Le Ried', 'Riedstraße');
insert or replace into cts_stops values('Général de Gaulle', 'General-de-Gaulle-Straße');
insert or replace into cts_stops values('Hoenheim Gare', 'Hohenheim Bf');

insert or replace into cts_stops values('Faubourg de Saverne Les Halles', 'Zaberner Vorstadt/Einkaufszentrum');
insert or replace into cts_stops values('Gallia', 'Gallia');
insert or replace into cts_stops values('Université', 'Universität');
insert or replace into cts_stops values('Observatoire', 'Planetarium');

insert or replace into cts_stops values('Esplanade', 'Esplanade');
insert or replace into cts_stops values('Winston Churchill', 'Winston-Churchill-Allee');
insert or replace into cts_stops values('Landsberg', 'Landsbergstraße');
insert or replace into cts_stops values('Jean Jaures', 'Jean-Jaures-Straße');
insert or replace into cts_stops values('Lycée Jean Monnet', 'Jean-Monnet-Gymnasium');
insert or replace into cts_stops values('Graviere Stade de la Meinau', 'Gravièrestraße/Meinaustadion');
insert or replace into cts_stops values('Kibitzenau', 'Kibitzenau');
insert or replace into cts_stops values('Saint Christophe', 'Christophskirche');
insert or replace into cts_stops values('Neuhof Rodolphe Reuss', 'Neuhof Reussallee');

insert or replace into cts_stops values('Poteries', 'Töpferei');
insert or replace into cts_stops values('Marcel Rudloff', 'Marcel-Rudloff-Gymnasium');
insert or replace into cts_stops values('Paul Eluard', 'Paul-Eluard-Straße');
insert or replace into cts_stops values('Etoile Polygone', 'Polygonstraße/Sternpark');
insert or replace into cts_stops values('Aristide Briand', 'Aristide-Briand-Straße');
insert or replace into cts_stops values('Citadelle', 'Zitadelle');
insert or replace into cts_stops values('Starcoop', 'Starcoop');
insert or replace into cts_stops values('Port du Rhin', 'Rheinhafen');
insert or replace into cts_stops values('Kehl Bahnhof', 'Gare du Kehl');
insert or replace into cts_stops values('Hochschule / Läger', 'Kehl Université');
insert or replace into cts_stops values('Kehl Rathaus', 'Kehl Hôtel de ville');

insert or replace into cts_stops values('Robertsau L''Escale', 'Robertsau Gemeindezentrum');
insert or replace into cts_stops values('Mélanie', 'Mélaniestraße');
insert or replace into cts_stops values('Jardiniers', 'Gärtnerblick');
insert or replace into cts_stops values('Boecklin', 'Böcklinstraße');
insert or replace into cts_stops values('Droits de l''Homme', 'Straße der Menschenrechte');
insert or replace into cts_stops values('Parlement Européen', 'Europäisches Parlament');

insert or replace into cts_stops values('Wolfisheim Henri Rendu', 'Wolfisheim Henri-Rendu-Platz');
insert or replace into cts_stops values('Parc d''activités d''Eckbolsheim Zénith', 'Eckbolsheim Gewerbegebiet/Zénith');
insert or replace into cts_stops values('Bois Romain', 'Römerwald');
insert or replace into cts_stops values('Eckelse', 'Eckelse');
insert or replace into cts_stops values('Octroi', 'Alter Zoll');
insert or replace into cts_stops values('Hohberg', 'Hohberg');
insert or replace into cts_stops values('Gruber', 'David-Gruber-Straße');
insert or replace into cts_stops values('Comtes', 'Grafenstraße');
insert or replace into cts_stops values('Parc des Romains', 'Römerpark');
insert or replace into cts_stops values('Porte Blanche', 'Weißes Tor');
insert or replace into cts_stops values('Place d''Islande', 'Inselplatz');

insert or replace into cts_stops values('Rotterdam', 'Rotterdammer Straße');
insert or replace into cts_stops values('Stade Vauban', 'Emile-Stahl-Stadion');
insert or replace into cts_stops values('Parc de la Citadelle', 'Zitadellenpark');
insert or replace into cts_stops values('Danube Le Vaisseau', 'Donaubrücke/Le Vaisseau');
insert or replace into cts_stops values('Presqu''ile André Malraux', 'André-Malraux-Halbinsel');
insert or replace into cts_stops values('Hôtel de Police', 'Polizei');
insert or replace into cts_stops values('Hôpital Civil', 'Allgemeines Krankenhaus');
insert or replace into cts_stops values('Lycée Pasteur', 'Louis-Pasteur-Schulen');
insert or replace into cts_stops values('Wilson Les Halles', 'Präsident-Woodrow-Wilson-Straße/Einkaufszentrum');
insert or replace into cts_stops values('Gare aux Marchandises', 'Güterbahnhof');
insert or replace into cts_stops values('Hochfelden', 'Hochfelder Straße');
insert or replace into cts_stops values('Rieth', 'Riethstraße');
insert or replace into cts_stops values('Lavoisier', 'Lavoisierstraße');
insert or replace into cts_stops values('Arago', 'François-Arago-Platz');
insert or replace into cts_stops values('Copenhague', 'Kopenhagener Straße');
insert or replace into cts_stops values('Londres', 'Londoner Straße');
insert or replace into cts_stops values('Vienne', 'Wiener Straße');
insert or replace into cts_stops values('Chambre de Métiers', 'Handwerkskammer');
insert or replace into cts_stops values('Espace Européen de l''Entreprise', 'Europäisches Gewerbegebiet');

insert or replace into cts_stops values('Travail', 'Arbeitsagentur');
insert or replace into cts_stops values('Place de Pierre', 'Pierrevorstadt Hauptplatz');
insert or replace into cts_stops values('Phalsbourg', 'Pfalzburger Straße');
insert or replace into cts_stops values('Clemenceau', 'Georges-Clemenceau-Boulevard');
insert or replace into cts_stops values('Palais de la musique et des Congres', 'Musik- und Kongreßpalast');
