#!/usr/bin/env perl

use strict;
use warnings;

use JSON;
use Travel::Status::DE::HAFAS;
use DateTime;

sub  trim { my $s = shift; $s =~ s/^\s+|\s+$//g; return $s };

my $dt = DateTime->now(time_zone=>'Europe/Berlin');
if ($ARGV[2]) {
	$dt = DateTime->from_epoch(epoch=>$ARGV[2], time_zone=>'Europe/Berlin');
}

my $hafas = Travel::Status::DE::HAFAS->new(
	service => $ARGV[0],
	station => $ARGV[1],
	datetime => $dt
);
if (my @results = $hafas->results) {
	my @trains;
	for my $train (@results) {
		push(@trains, {
			id=>$train->id,
			type=>trim($train->type),
			line=>$train->line_no,
			number=>$train->number,
			direction=>$train->direction,
			station=>$train->station,
			scheduled=>$train->sched_datetime->epoch,
			realtime=>defined $train->rt_datetime ? $train->rt_datetime->epoch : JSON::null,
			delay=>defined $train->rt_datetime ? ($train->rt_datetime->epoch - $train->sched_datetime->epoch)/60 : JSON::null,
		});
	}
	print encode_json({
		trains=>[@trains]
	});
} else {
	print encode_json({
		error_code => $hafas->errcode,
		error_string => $hafas->errstr
	});
}
