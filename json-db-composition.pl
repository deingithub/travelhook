#!/usr/bin/env perl

use strict;
use warnings;

use JSON;
use DateTime;
use Travel::Status::DE::DBRIS;

# ./json-db-composition.pl DEPARTURE_EPOCH DEPARTURE_UIC TRAINTYPE TRAINNUMBER

my $wr = Travel::Status::DE::DBRIS->new(
	formation => {
		departure => DateTime->from_epoch(epoch=>$ARGV[0], time_zone=>'Europe/Berlin'),
		eva => $ARGV[1],
		train_type => $ARGV[2],
		train_number => $ARGV[3],
	},
);
if (my $errstr = $wr->errstr) {
	print encode_json({
		error_string => $wr->errstr
	});
} else {
	print to_json({groups=>[$wr->result->groups]}, {convert_blessed=>1, utf8=>1});
}
