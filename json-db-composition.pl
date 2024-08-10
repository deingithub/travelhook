#!/usr/bin/env perl

use strict;
use warnings;

use JSON;
use DateTime;
use Travel::Status::DE::DBWagenreihung;

# ./json-db-composition.pl DEPARTURE_EPOCH DEPARTURE_UIC TRAINTYPE TRAINNUMBER

my $result = Travel::Status::DE::DBWagenreihung->new(
	departure => DateTime->from_epoch(epoch=>$ARGV[0], time_zone=>'Europe/Berlin'),
	eva => $ARGV[1],
	train_type => $ARGV[2],
	train_number => $ARGV[3],
);
if (my $errstr = $result->errstr) {
	print encode_json({
		error_string => $result->errstr
	});
} else {
	print to_json({groups=>[$result->groups]}, {convert_blessed=>1, utf8=>1});
}
