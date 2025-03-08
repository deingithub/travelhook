#!/usr/bin/env perl

use strict;
use warnings;

use JSON;
use Travel::Status::DE::DBRIS;

my $ris = Travel::Status::DE::DBRIS->new(
	locationSearch => $ARGV[0]
);
if (my @results = $ris->results) {
	my @ret;
	foreach my $stop (@results) {
		push(@ret, {
			name => $stop->{name},
			eva => $stop->{eva},
		});
	}

	print encode_json({
		stops=>[@ret]
	});
} else {
	print encode_json({
		error_string => $ris->errstr
	});
}
