#!/usr/bin/env perl

use strict;
use warnings;

use JSON;
use Travel::Status::DE::DBWagenreihung;

my $result = Travel::Status::DE::DBWagenreihung->new(
	train_number => $ARGV[0],
	departure => $ARGV[1]
);
if (my $errstr = $result->errstr) {
	print encode_json({
		error_string => $result->errstr
	});
} else {
	my @wagons = $result->wagons;
	my @groups;
	for my $group (@{$result->{wagongroups}}) {
		my @group_wagons;
		for my $wagon (@{$group}) {
			push(
				@group_wagons, $wagon->TO_JSON
			);
		}
		push(@groups, [@group_wagons]);
	}
	print encode_json(
		{groups=>[@groups]},
	);
}
