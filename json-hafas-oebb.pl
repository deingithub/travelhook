#!/usr/bin/env perl

use strict;
use warnings;

use JSON;
use Travel::Status::DE::HAFAS;

my $result = Travel::Status::DE::HAFAS->new(
	service => chr(214) . "BB",
	journey => {id => $ARGV[0]},
	with_polyline=>1
);
if (my $status = $result->result) {
	my @polyline;
	my $only_eva = 1;
	foreach my $point ($status->polyline) {
		if (not defined $point->{eva}) {
			$only_eva=0;
		}
		push(@polyline, {
			lat=>$point->{lat},
			lon=>$point->{lon},
			eva=>$point->{eva},
			name=>$point->{name}
		});
	}
	my @route;
	for my $stop ($status->route) {
		push(@route, {
			sched_arr=>defined $stop->sched_arr ? $stop->sched_arr->epoch : JSON::null,
			rt_arr=>defined $stop->rt_arr ? $stop->rt_arr->epoch : JSON::null,
			arr_delay=>$stop->arr_delay // JSON::null,
			sched_dep=>defined $stop->sched_dep ? $stop->sched_dep->epoch : JSON::null,
			rt_dep=>defined $stop->rt_dep ? $stop->rt_dep->epoch : JSON::null,
			dep_delay=>$stop->dep_delay // JSON::null,
			name=>$stop->loc->name,
			lat=>$stop->loc->lat,
			lon=>$stop->loc->lon,
			eva=>$stop->loc->eva,
		});
	}
	my @messages;
	foreach my $message ($status->messages) {
		push(@messages, {
			short=>$message->short,
			text=>$message->text,
			code=>$message->code,
			type=>$message->type,
		});
	}
	print encode_json({
		id=>$status->id,
		operator=>$status->operator,
		direction=>$status->direction,
		polyline=>[@polyline],
		beeline=>$only_eva,
		messages=>[@messages],
		route=>[@route]
	});
} else {
	print encode_json({
		error_code => $result->errcode,
		error_string => $result->errstr
	});
}
