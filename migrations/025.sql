-- tram number database
CREATE TABLE trams (
	network TEXT NOT NULL,
	individual_number INTEGER,
	number_from INTEGER,
	number_to INTEGER,
	description TEXT NOT NULL,
	PRIMARY KEY(network,individual_number,number_from,number_to)
);
INSERT INTO trams VALUES ('KVV', NULL, 221, 265, 'GT6');
INSERT INTO trams VALUES ('KVV', NULL, 301, 325, 'GT8');
INSERT INTO trams VALUES ('KVV', NULL, 326, 400, 'NET 2012');
INSERT INTO trams VALUES ('KVV', NULL, 801, 836, 'Hochflurer');
INSERT INTO trams VALUES ('KVV', NULL, 837, 922, 'Mittelflurer');
INSERT INTO trams VALUES ('KVV', NULL, 923, 984, 'ET 2010');

INSERT INTO trams VALUES ('KVV', 930, NULL, NULL, '🟩 ET 2010');
INSERT INTO trams VALUES ('KVV', 915, NULL, NULL, '🟩 Mittelflurer');
INSERT INTO trams VALUES ('KVV', 355, NULL, NULL, '🟩 NET 2012');
INSERT INTO trams VALUES ('KVV', 233, NULL, NULL, 'GT6 "init"');
INSERT INTO trams VALUES ('KVV', 248, NULL, NULL, 'GT6 "init"');
INSERT INTO trams VALUES ('KVV', 257, NULL, NULL, 'GT6 "init"');
INSERT INTO trams VALUES ('KVV', 261, NULL, NULL, 'GT6 "init"');
INSERT INTO trams VALUES ('KVV', 846, NULL, NULL, 'Mittelflurer "RegioBistro"');
INSERT INTO trams VALUES ('KVV', 847, NULL, NULL, 'Mittelflurer "RegioBistro"');
INSERT INTO trams VALUES ('KVV', 848, NULL, NULL, 'Mittelflurer "RegioBistro"');


INSERT INTO trams VALUES('RNV', NULL, 1031, 1032, '8MGT [LU]');
INSERT INTO trams VALUES('RNV', NULL, 1041, 1043, '8MGT [RHB]');
INSERT INTO trams VALUES('RNV', NULL, 2201, 2214, '6MGT [LU]');
INSERT INTO trams VALUES('RNV', NULL, 2215, 2222, 'RNV6 [LU]');

INSERT INTO trams VALUES('RNV', NULL, 3251, 3258, 'M8C-NF [HD]');
INSERT INTO trams VALUES('RNV', NULL, 3261, 3272, 'MGT6D [HD]');
INSERT INTO trams VALUES('RNV', NULL, 3273, 3288, 'RNV8 [HD]');

INSERT INTO trams VALUES('RNV', NULL, 4117, 4122, 'V6 [OEG]');
INSERT INTO trams VALUES('RNV', NULL, 4123, 4162, 'RNV6 [OEG]');

INSERT INTO trams VALUES('RNV', NULL, 5601, 5650, '6MGT [MA]');
INSERT INTO trams VALUES('RNV', NULL, 5701, 5716, 'RNV8 [MA]');
INSERT INTO trams VALUES('RNV', NULL, 5761, 5763, 'RNV6 [MA]');

INSERT INTO trams VALUES('RNV', NULL, 1401, 1499, 'RNT 30');
INSERT INTO trams VALUES('RNV', NULL, 1501, 1599, 'RNT 60');
INSERT INTO trams VALUES('RNV', NULL, 1801, 1899, 'RNT 40');

INSERT INTO trams VALUES('WL', NULL, 4001, 4098, 'E₂');
INSERT INTO trams VALUES('WL', NULL, 4301, 4342, 'E₂');
INSERT INTO trams VALUES('WL', NULL, 1401, 1517, 'c₅');
INSERT INTO trams VALUES('WL', NULL, 1, 51, 'ULF A');
INSERT INTO trams VALUES('WL', NULL, 52, 131, 'ULF A₁');
INSERT INTO trams VALUES('WL', NULL, 601, 701, 'ULF B');
INSERT INTO trams VALUES('WL', NULL, 702, 801, 'ULF B₁');
INSERT INTO trams VALUES('WL', NULL, 301, 456, 'Flexity Wien'); -- currently only until 446, with all options max. 456
INSERT INTO trams VALUES('WL', 614, NULL, NULL, 'ULF B "Flexity"');

INSERT INTO trams VALUES('WL', NULL, 2001, 2062, 'Type U');
INSERT INTO trams VALUES('WL', NULL, 2063, 2136, 'Type U₂');
INSERT INTO trams VALUES('WL', NULL, 2201, 2209, 'Type U₁');
INSERT INTO trams VALUES('WL', NULL, 2210, 2317, 'Type U₁₁');
INSERT INTO trams VALUES('WL', NULL, 3801, 3924, 'Type V'); -- only the driving coaches
INSERT INTO trams VALUES('WL', 3701, NULL, NULL, 'FeliX');
INSERT INTO trams VALUES('WL', 3702, NULL, NULL, 'FeliX');
INSERT INTO trams VALUES('WL', NULL, 3701, 3790, 'Type X'); -- only the driving coaches again
INSERT INTO trams VALUES('WL', NULL, 2601, 2678, 'Type T');
INSERT INTO trams VALUES('WL', NULL, 2679, 2744, 'Type T₁');
