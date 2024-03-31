#!/usr/bin/env perl

use strict;
use warnings;

use JSON;
use Travel::Status::DE::DBWagenreihung;
use Travel::Status::DE::DBWagenreihung::Wagon;

my $result = Travel::Status::DE::DBWagenreihung->new(
	train_number => $ARGV[0],
	departure => $ARGV[1]
);
if (my $errstr = $result->errstr) {
	print encode_json({
		error_string => $result->errstr
	});
} else {
	print encode_json({groups=>[$result->wgroups]});
}
