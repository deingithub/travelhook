#!/usr/bin/env perl

use strict;
use warnings;

use JSON;
use Travel::Status::DE::HAFAS;

my $stopfinder = Travel::Status::DE::HAFAS->new(
	service => chr(214) . "BB",
	locationSearch => $ARGV[0],
);
if (my @locs = $stopfinder->results) {
	my @stops;
	for my $loc (@locs) {
		push(@stops, {
			name=>$loc->name,
			eva=>$loc->eva
		});
	}
	print encode_json({
		stops=> [@stops]
	});
} else {
	print encode_json({
		error_code => $stopfinder->errcode,
		error_string => $stopfinder->errstr
	});
}
