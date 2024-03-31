CREATE TABLE trainset_names(
	identifier TEXT,
	name TEXT
);

-- data from https:--github.com/marudor/bahn.expert/blob/main/src/server/coachSequence/TrainNames.ts
-- arguably questionable if this even falls under copyright or constitutes a "substantial portion" of the software but just to make sure:
-- MIT License
-- Copyright (c) 2017 marudor
-- Permission is hereby granted, free of charge, to any person obtaining a copy
-- of this software and associated documentation files (the "Software"), to deal
-- in the Software without restriction, including without limitation the rights
-- to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
-- copies of the Software, and to permit persons to whom the Software is
-- furnished to do so, subject to the following conditions:
--  The above copyright notice and this permission notice shall be included in all
--  copies or substantial portions of the Software.
-- THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
-- IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
-- FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
-- AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
-- LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
-- OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
-- SOFTWARE.

begin transaction;
INSERT INTO trainset_names VALUES('ICE0101', 'Gießen');
INSERT INTO trainset_names VALUES('ICE0102', 'Jever');
INSERT INTO trainset_names VALUES('ICE0103', 'Neu-Isenburg');
INSERT INTO trainset_names VALUES('ICE0104', 'Fulda');
INSERT INTO trainset_names VALUES('ICE0105', 'Offenbach am Main');
INSERT INTO trainset_names VALUES('ICE0106', 'Itzehoe');
INSERT INTO trainset_names VALUES('ICE0107', 'Plattling');
INSERT INTO trainset_names VALUES('ICE0108', 'Lichtenfels');
INSERT INTO trainset_names VALUES('ICE0110', 'Gelsenkirchen');
INSERT INTO trainset_names VALUES('ICE0111', 'Nürnberg');
INSERT INTO trainset_names VALUES('ICE0112', 'Memmingen');
INSERT INTO trainset_names VALUES('ICE0113', 'Frankenthal/Pfalz');
INSERT INTO trainset_names VALUES('ICE0114', 'Friedrichshafen');
INSERT INTO trainset_names VALUES('ICE0115', 'Regensburg');
INSERT INTO trainset_names VALUES('ICE0116', 'Pforzheim');
INSERT INTO trainset_names VALUES('ICE0117', 'Hof');
INSERT INTO trainset_names VALUES('ICE0119', 'Osnabrück');
INSERT INTO trainset_names VALUES('ICE0120', 'Lüneburg');
INSERT INTO trainset_names VALUES('ICE0152', 'Hanau');
INSERT INTO trainset_names VALUES('ICE0153', 'Neumünster');
INSERT INTO trainset_names VALUES('ICE0154', 'Flensburg');
INSERT INTO trainset_names VALUES('ICE0155', 'Rosenheim');
INSERT INTO trainset_names VALUES('ICE0156', 'Heppenheim/Bergstraße');
INSERT INTO trainset_names VALUES('ICE0157', 'Landshut');
INSERT INTO trainset_names VALUES('ICE0158', 'Gütersloh');
INSERT INTO trainset_names VALUES('ICE0159', 'Bad Oldesloe');
INSERT INTO trainset_names VALUES('ICE0160', 'Mülheim an der Ruhr');
INSERT INTO trainset_names VALUES('ICE0161', 'Bebra');
INSERT INTO trainset_names VALUES('ICE0162', 'Geisenheim/Rheingau');
INSERT INTO trainset_names VALUES('ICE0166', 'Gelnhausen');
INSERT INTO trainset_names VALUES('ICE0167', 'Garmisch-Partenkirchen');
INSERT INTO trainset_names VALUES('ICE0168', 'Crailsheim');
INSERT INTO trainset_names VALUES('ICE0169', 'Worms');
INSERT INTO trainset_names VALUES('ICE0171', 'Heusenstamm');
INSERT INTO trainset_names VALUES('ICE0172', 'Aschaffenburg');
INSERT INTO trainset_names VALUES('ICE0173', 'Basel');
INSERT INTO trainset_names VALUES('ICE0174', 'Zürich');
INSERT INTO trainset_names VALUES('ICE0175', 'Nürnberg');
INSERT INTO trainset_names VALUES('ICE0176', 'Bremen');
INSERT INTO trainset_names VALUES('ICE0177', 'Rendsburg');
INSERT INTO trainset_names VALUES('ICE0178', 'Bremerhaven');
INSERT INTO trainset_names VALUES('ICE0180', 'Castrop-Rauxel');
INSERT INTO trainset_names VALUES('ICE0181', 'Interlaken');
INSERT INTO trainset_names VALUES('ICE0182', 'Rüdesheim am Rhein');
INSERT INTO trainset_names VALUES('ICE0183', 'Timmendorfer Strand');
INSERT INTO trainset_names VALUES('ICE0184', 'Bruchsal');
INSERT INTO trainset_names VALUES('ICE0185', 'Freilassing');
INSERT INTO trainset_names VALUES('ICE0186', 'Chur');
INSERT INTO trainset_names VALUES('ICE0187', 'Mühldorf a. Inn');
INSERT INTO trainset_names VALUES('ICE0188', 'Hildesheim');
INSERT INTO trainset_names VALUES('ICE0190', 'Ludwigshafen am Rhein');
--
-- ICE 2 - BR 402
INSERT INTO trainset_names VALUES('ICE0201', 'Rheinsberg');
INSERT INTO trainset_names VALUES('ICE0202', 'Wuppertal');
INSERT INTO trainset_names VALUES('ICE0203', 'Cottbus/Chóśebuz');
INSERT INTO trainset_names VALUES('ICE0204', 'Bielefeld');
INSERT INTO trainset_names VALUES('ICE0205', 'Zwickau');
INSERT INTO trainset_names VALUES('ICE0206', 'Magdeburg');
INSERT INTO trainset_names VALUES('ICE0207', 'Stendal');
INSERT INTO trainset_names VALUES('ICE0208', 'Bonn');
INSERT INTO trainset_names VALUES('ICE0209', 'Riesa');
INSERT INTO trainset_names VALUES('ICE0210', 'Fontanestadt Neuruppin');
INSERT INTO trainset_names VALUES('ICE0211', 'Uelzen');
INSERT INTO trainset_names VALUES('ICE0212', 'Potsdam');
INSERT INTO trainset_names VALUES('ICE0213', 'Nauen');
INSERT INTO trainset_names VALUES('ICE0214', 'Hamm (Westf.)');
INSERT INTO trainset_names VALUES('ICE0215', 'Bitterfeld-Wolfen');
INSERT INTO trainset_names VALUES('ICE0216', 'Dessau');
INSERT INTO trainset_names VALUES('ICE0217', 'Bergen auf Rügen');
INSERT INTO trainset_names VALUES('ICE0218', 'Braunschweig');
INSERT INTO trainset_names VALUES('ICE0219', 'Hagen');
INSERT INTO trainset_names VALUES('ICE0220', 'Meiningen');
INSERT INTO trainset_names VALUES('ICE0221', 'Lübbenau/Spreewald');
INSERT INTO trainset_names VALUES('ICE0222', 'Eberswalde');
INSERT INTO trainset_names VALUES('ICE0223', 'Schwerin');
INSERT INTO trainset_names VALUES('ICE0224', 'Saalfeld (Saale)');
INSERT INTO trainset_names VALUES('ICE0225', 'Oldenburg (Oldb)');
INSERT INTO trainset_names VALUES('ICE0226', 'Lutherstadt Wittenberg');
INSERT INTO trainset_names VALUES('ICE0227', 'Ludwigslust');
INSERT INTO trainset_names VALUES('ICE0228', 'Altenburg');
INSERT INTO trainset_names VALUES('ICE0229', 'Templin');
INSERT INTO trainset_names VALUES('ICE0230', 'Delitzsch');
INSERT INTO trainset_names VALUES('ICE0231', 'Brandenburg an der Havel');
INSERT INTO trainset_names VALUES('ICE0232', 'Frankfurt (Oder)');
INSERT INTO trainset_names VALUES('ICE0233', 'Ulm');
INSERT INTO trainset_names VALUES('ICE0234', 'Minden');
INSERT INTO trainset_names VALUES('ICE0235', 'Görlitz');
INSERT INTO trainset_names VALUES('ICE0236', 'Jüterbog');
INSERT INTO trainset_names VALUES('ICE0237', 'Neustrelitz');
INSERT INTO trainset_names VALUES('ICE0238', 'Saarbrücken');
INSERT INTO trainset_names VALUES('ICE0239', 'Essen');
INSERT INTO trainset_names VALUES('ICE0240', 'Bochum');
INSERT INTO trainset_names VALUES('ICE0241', 'Bad Hersfeld');
INSERT INTO trainset_names VALUES('ICE0242', 'Quedlinburg');
INSERT INTO trainset_names VALUES('ICE0243', 'Bautzen/Budyšin');
INSERT INTO trainset_names VALUES('ICE0244', 'Koblenz');
--
-- ICE 3 - BR 403
INSERT INTO trainset_names VALUES('ICE0301', 'Freiburg im Breisgau');
INSERT INTO trainset_names VALUES('ICE0302', 'Hansestadt Lübeck');
INSERT INTO trainset_names VALUES('ICE0303', 'Dortmund');
INSERT INTO trainset_names VALUES('ICE0304', '🏳️‍🌈 München');
INSERT INTO trainset_names VALUES('ICE0305', 'Baden-Baden');
INSERT INTO trainset_names VALUES('ICE0306', 'Nördlingen');
INSERT INTO trainset_names VALUES('ICE0307', 'Oberhausen');
INSERT INTO trainset_names VALUES('ICE0308', 'Murnau am Staffelsee');
INSERT INTO trainset_names VALUES('ICE0309', 'Aalen');
INSERT INTO trainset_names VALUES('ICE0310', 'Wolfsburg');
INSERT INTO trainset_names VALUES('ICE0311', 'Wiesbaden');
INSERT INTO trainset_names VALUES('ICE0312', 'Montabaur');
INSERT INTO trainset_names VALUES('ICE0313', 'Treuchtlingen');
INSERT INTO trainset_names VALUES('ICE0314', 'Bergisch Gladbach');
INSERT INTO trainset_names VALUES('ICE0315', 'Singen (Hohentwiel)');
INSERT INTO trainset_names VALUES('ICE0316', 'Siegburg');
INSERT INTO trainset_names VALUES('ICE0317', 'Recklinghausen');
INSERT INTO trainset_names VALUES('ICE0318', 'Münster (Westf.)');
INSERT INTO trainset_names VALUES('ICE0319', 'Duisburg');
INSERT INTO trainset_names VALUES('ICE0320', 'Weil am Rhein');
INSERT INTO trainset_names VALUES('ICE0321', 'Krefeld');
INSERT INTO trainset_names VALUES('ICE0322', 'Solingen');
INSERT INTO trainset_names VALUES('ICE0323', 'Schaffhausen');
INSERT INTO trainset_names VALUES('ICE0324', 'Fürth');
INSERT INTO trainset_names VALUES('ICE0325', 'Ravensburg');
INSERT INTO trainset_names VALUES('ICE0326', 'Neunkirchen');
INSERT INTO trainset_names VALUES('ICE0327', 'Siegen');
INSERT INTO trainset_names VALUES('ICE0328', 'Aachen');
INSERT INTO trainset_names VALUES('ICE0330', 'Göttingen');
INSERT INTO trainset_names VALUES('ICE0331', 'Westerland/Sylt');
INSERT INTO trainset_names VALUES('ICE0332', 'Augsburg');
INSERT INTO trainset_names VALUES('ICE0333', 'Goslar');
INSERT INTO trainset_names VALUES('ICE0334', 'Offenburg');
INSERT INTO trainset_names VALUES('ICE0335', 'Konstanz');
INSERT INTO trainset_names VALUES('ICE0336', 'Ingolstadt');
INSERT INTO trainset_names VALUES('ICE0337', 'Stuttgart');
INSERT INTO trainset_names VALUES('ICE0351', 'Herford');
INSERT INTO trainset_names VALUES('ICE0352', 'Mönchengladbach');
INSERT INTO trainset_names VALUES('ICE0353', 'Neu-Ulm');
INSERT INTO trainset_names VALUES('ICE0354', 'Mittenwald');
INSERT INTO trainset_names VALUES('ICE0355', 'Tuttlingen');
INSERT INTO trainset_names VALUES('ICE0357', 'Esslingen am Neckar');
INSERT INTO trainset_names VALUES('ICE0358', 'St. Ingbert');
INSERT INTO trainset_names VALUES('ICE0359', 'Leverkusen');
INSERT INTO trainset_names VALUES('ICE0360', 'Linz am Rhein');
INSERT INTO trainset_names VALUES('ICE0361', 'Celle');
INSERT INTO trainset_names VALUES('ICE0362', 'Schwerte (Ruhr)');
INSERT INTO trainset_names VALUES('ICE0363', 'Weilheim i. OB');
--
-- ICE T - BR 411
INSERT INTO trainset_names VALUES('ICE1101', 'Neustadt an der Weinstraße');
INSERT INTO trainset_names VALUES('ICE1102', 'Neubrandenburg');
INSERT INTO trainset_names VALUES('ICE1103', 'Paderborn');
INSERT INTO trainset_names VALUES('ICE1104', 'Erfurt');
INSERT INTO trainset_names VALUES('ICE1105', 'Dresden');
INSERT INTO trainset_names VALUES('ICE1107', 'Pirna');
INSERT INTO trainset_names VALUES('ICE1108', 'Berlin');
INSERT INTO trainset_names VALUES('ICE1109', 'Güstrow');
INSERT INTO trainset_names VALUES('ICE1110', 'Naumburg (Saale)');
INSERT INTO trainset_names VALUES('ICE1111', 'Hansestadt Wismar');
INSERT INTO trainset_names VALUES('ICE1112', 'Freie und Hansestadt Hamburg');
INSERT INTO trainset_names VALUES('ICE1113', 'Hansestadt Stralsund');
INSERT INTO trainset_names VALUES('ICE1117', 'Erlangen');
INSERT INTO trainset_names VALUES('ICE1118', 'Plauen/Vogtland');
INSERT INTO trainset_names VALUES('ICE1119', 'Meißen');
INSERT INTO trainset_names VALUES('ICE1125', 'Arnstadt');
INSERT INTO trainset_names VALUES('ICE1126', 'Leipzig');
INSERT INTO trainset_names VALUES('ICE1127', 'Weimar');
INSERT INTO trainset_names VALUES('ICE1128', 'Reutlingen');
INSERT INTO trainset_names VALUES('ICE1129', 'Kiel');
INSERT INTO trainset_names VALUES('ICE1130', 'Jena');
INSERT INTO trainset_names VALUES('ICE1131', 'Trier');
INSERT INTO trainset_names VALUES('ICE1132', 'Wittenberge');
INSERT INTO trainset_names VALUES('ICE1151', 'Elsterwerda');
INSERT INTO trainset_names VALUES('ICE1152', 'Travemünde');
INSERT INTO trainset_names VALUES('ICE1153', 'Ilmenau');
INSERT INTO trainset_names VALUES('ICE1154', 'Sonneberg');
INSERT INTO trainset_names VALUES('ICE1155', 'Mühlhausen/Thüringen');
INSERT INTO trainset_names VALUES('ICE1156', 'Waren (Müritz)');
INSERT INTO trainset_names VALUES('ICE1157', 'Innsbruck');
INSERT INTO trainset_names VALUES('ICE1158', 'Falkenberg/Elster');
INSERT INTO trainset_names VALUES('ICE1159', 'Passau');
INSERT INTO trainset_names VALUES('ICE1160', 'Markt Holzkirchen');
INSERT INTO trainset_names VALUES('ICE1161', 'Andernach');
INSERT INTO trainset_names VALUES('ICE1162', 'Vaihingen an der Enz');
INSERT INTO trainset_names VALUES('ICE1163', 'Ostseebad Binz');
INSERT INTO trainset_names VALUES('ICE1164', 'Rödental');
INSERT INTO trainset_names VALUES('ICE1165', 'Bad Oeynhausen');
INSERT INTO trainset_names VALUES('ICE1166', 'Bingen am Rhein');
INSERT INTO trainset_names VALUES('ICE1167', 'Traunstein');
INSERT INTO trainset_names VALUES('ICE1168', 'Ellwangen');
INSERT INTO trainset_names VALUES('ICE1169', 'Tutzing');
INSERT INTO trainset_names VALUES('ICE1170', 'Prenzlau');
INSERT INTO trainset_names VALUES('ICE1171', 'Oschatz');
INSERT INTO trainset_names VALUES('ICE1172', 'Bamberg');
INSERT INTO trainset_names VALUES('ICE1173', 'Halle (Saale)');
INSERT INTO trainset_names VALUES('ICE1174', 'Hansestadt Warburg');
INSERT INTO trainset_names VALUES('ICE1175', 'Villingen-Schwenningen');
INSERT INTO trainset_names VALUES('ICE1176', 'Coburg');
INSERT INTO trainset_names VALUES('ICE1177', 'Rathenow');
INSERT INTO trainset_names VALUES('ICE1178', 'Ostseebad Warnemünde');
INSERT INTO trainset_names VALUES('ICE1180', 'Darmstadt');
INSERT INTO trainset_names VALUES('ICE1181', 'Horb am Neckar');
INSERT INTO trainset_names VALUES('ICE1182', 'Mainz');
INSERT INTO trainset_names VALUES('ICE1183', 'Oberursel (Taunus)');
INSERT INTO trainset_names VALUES('ICE1184', 'Kaiserslautern');
INSERT INTO trainset_names VALUES('ICE1190', 'Wien');
INSERT INTO trainset_names VALUES('ICE1191', 'Salzburg');
INSERT INTO trainset_names VALUES('ICE1192', 'Linz');
--
-- ICE T - BR 415
INSERT INTO trainset_names VALUES('ICE1501', 'Eisenach');
INSERT INTO trainset_names VALUES('ICE1502', 'Karlsruhe');
INSERT INTO trainset_names VALUES('ICE1503', 'Altenbeken');
INSERT INTO trainset_names VALUES('ICE1504', 'Heidelberg');
INSERT INTO trainset_names VALUES('ICE1505', 'Marburg/Lahn');
INSERT INTO trainset_names VALUES('ICE1506', 'Kassel');
INSERT INTO trainset_names VALUES('ICE1520', 'Gotha');
INSERT INTO trainset_names VALUES('ICE1521', 'Homburg/Saar');
INSERT INTO trainset_names VALUES('ICE1522', 'Torgau');
INSERT INTO trainset_names VALUES('ICE1523', 'Hansestadt Greifswald');
INSERT INTO trainset_names VALUES('ICE1524', 'Hansestadt Rostock');
--
-- Intercity2
INSERT INTO trainset_names VALUES('ICD2853', 'Nationalpark Sächsische Schweiz');
INSERT INTO trainset_names VALUES('ICD2865', 'Remstal');
INSERT INTO trainset_names VALUES('ICD2868', 'Nationalpark Niedersächsisches Wattenmeer');
INSERT INTO trainset_names VALUES('ICD2871', 'Leipziger Neuseenland');
INSERT INTO trainset_names VALUES('ICD2874', 'Oberer Neckar');
INSERT INTO trainset_names VALUES('ICD2875', 'Magdeburger Börde');
--
-- Intercity2 KISS - BR 4110
INSERT INTO trainset_names VALUES('ICK4103', 'Allgäu');
INSERT INTO trainset_names VALUES('ICK4111', 'Gäu');
INSERT INTO trainset_names VALUES('ICK4114', 'Dresden Elbland');
INSERT INTO trainset_names VALUES('ICK4117', 'Mecklenburgische Ostseeküste');
--
-- ICE 3 - BR 406
INSERT INTO trainset_names VALUES('ICE4601', 'Europa/Europe');
INSERT INTO trainset_names VALUES('ICE4602', 'Euregio Maas-Rhein');
INSERT INTO trainset_names VALUES('ICE4603', 'Mannheim');
INSERT INTO trainset_names VALUES('ICE4604', 'Brussel/Bruxelles');
INSERT INTO trainset_names VALUES('ICE4607', 'Hannover');
INSERT INTO trainset_names VALUES('ICE4610', 'Frankfurt am Main');
INSERT INTO trainset_names VALUES('ICE4611', 'Düsseldorf');
INSERT INTO trainset_names VALUES('ICE4651', 'Amsterdam');
INSERT INTO trainset_names VALUES('ICE4652', 'Arnhem');
INSERT INTO trainset_names VALUES('ICE4680', 'Würzburg');
INSERT INTO trainset_names VALUES('ICE4682', 'Köln');
INSERT INTO trainset_names VALUES('ICE4683', 'Limburg an der Lahn');
INSERT INTO trainset_names VALUES('ICE4684', 'Forbach-Lorraine');
INSERT INTO trainset_names VALUES('ICE4685', 'Schwäbisch Hall');
--
-- ICE 3 - BR 407
INSERT INTO trainset_names VALUES('ICE4712', 'Dillingen a.d. Donau');
INSERT INTO trainset_names VALUES('ICE4710', 'Ansbach');
INSERT INTO trainset_names VALUES('ICE4717', 'Paris');
INSERT INTO trainset_names VALUES('ICE8007', 'Rheinland');
INSERT INTO trainset_names VALUES('ICE9006', 'Martin Luther');
INSERT INTO trainset_names VALUES('ICE9018', 'Freistaat Bayern');
INSERT INTO trainset_names VALUES('ICE9025', 'Nordrhein-Westfalen');
INSERT INTO trainset_names VALUES('ICE9026', 'Zürichsee');
INSERT INTO trainset_names VALUES('ICE9028', 'Freistaat Sachsen');
INSERT INTO trainset_names VALUES('ICE9041', 'Baden-Württemberg');
INSERT INTO trainset_names VALUES('ICE9046', 'Female ICE');
INSERT INTO trainset_names VALUES('ICE9050', 'Metropole Ruhr');
INSERT INTO trainset_names VALUES('ICE9202', 'Schleswig-Holstein');
INSERT INTO trainset_names VALUES('ICE9237', '#137 The final One');
INSERT INTO trainset_names VALUES('ICE9457', 'Bundesrepublik Deutschland');
INSERT INTO trainset_names VALUES('ICE9481', 'Rheinland-Pfalz');
commit;
