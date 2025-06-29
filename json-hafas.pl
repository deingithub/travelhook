#!/usr/bin/env perl

use strict;
use warnings;

use JSON;
use Travel::Status::DE::DBRIS;
use Travel::Status::DE::HAFAS;
use Travel::Status::MOTIS;

if ($ARGV[0] =~ /^MOTIS-/) {
	my $service = substr($ARGV[0],6);
	my $motis = Travel::Status::MOTIS->new(
		service => $service,
		trip_id => $ARGV[1]
	);
	if (my $status = $motis->result) {
		my @polyline;
		foreach my $point ($status->polyline) {
			push(@polyline, {
				lat=>$point->{lat},
				lon=>$point->{lon},
				eva=>JSON::null,
				name=>JSON::null
			});
		}
		my @messages; # unused
		my %stop_messages; # unused
		my @route;
		foreach my $stop ($status->stopovers) {
			push(@route, {
				name=>$stop->stop->name,
				eva=>$stop->stop->id,
				sched_arr => defined $stop->{scheduled_arrival} ? $stop->{scheduled_arrival}->epoch : JSON::null,
				sched_dep => defined $stop->{scheduled_departure} ? $stop->{scheduled_departure}->epoch : JSON::null,
				rt_arr => defined $stop->{realtime_arrival} ? $stop->{realtime_arrival}->epoch : JSON::null,
				rt_dep => defined $stop->{realtime_departure} ? $stop->{realtime_departure}->epoch : JSON::null,
			});
		}
		my $only_eva = 0;
		if ($#route == $#polyline) {
			$only_eva = 1;
		}
		print encode_json({
			id=>$status->id,
			operator=>$status->agency,
			direction=>$status->headsign,
			no=>0,
			polyline=>[@polyline],
			beeline=>$only_eva,
			route=>[@route],
			messages=>[@messages],
			stop_messages=>{%stop_messages}
		});
		exit 0;
	} else {
		print encode_json({
			error_code => 'motis broke rip',
			error_string => $motis->errstr
		});
		exit 1;
	}
}

if ($ARGV[0] eq 'DBRIS') {
	my @no_train_number_types = qw(Bus RNV S STB STR U);
	my $ris = Travel::Status::DE::DBRIS->new(
		journey => $ARGV[1]
	);
	if (my $result = $ris->result) {
		my @polyline;
		my @messages;
		my @route;

		my $i = 0;
		foreach my $stop ($result->route) {
			my $raw_stop = $result->{raw_route}[$i];
			my ($lon, $lat) = $raw_stop->{id} =~ /X=(\d+)\@Y=(\d+)/;
			push(@route, {
				name => $stop->{name},
				eva => $stop->{eva},
				sched_arr => defined $stop->{sched_arr} ? $stop->{sched_arr}->epoch : JSON::null,
				sched_dep => defined $stop->{sched_dep} ? $stop->{sched_dep}->epoch : JSON::null,
				rt_arr => defined $stop->{rt_arr} ? $stop->{rt_arr}->epoch : JSON::null,
				rt_dep => defined $stop->{rt_dep} ? $stop->{rt_dep}->epoch : JSON::null,
				lat=>$lat * 1e-6,
				lon=>$lon * 1e-6
			});

			push(@polyline, {
				name=>$stop->{name},
				eva=>$stop->{eva},
				lat=>$lat * 1e-6,
				lon=>$lon * 1e-6
			});
			$i++;
		}

		print encode_json({
			id=>$ARGV[1],
			operator=>JSON::null,
			direction=>$route[-1]->{name},
			polyline=>[@polyline],
			beeline=>1,
			route=>[@route],
			messages=>[$result->messages],
			stop_messages=>{}
		});
	} else {
		print encode_json({
			error_string => $ris->errstr
		});
	}
	exit 0;
}

my $result = Travel::Status::DE::HAFAS->new(
	service => $ARGV[0],
	journey => {id => $ARGV[1]},
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
			eva=>$point->{eva} // JSON::null,
			name=>$point->{name} // JSON::null
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
	my @route;
	my %stop_messages;
	foreach my $stop ($status->route) {
		push(@route, {
			name=>$stop->loc->name,
			eva=>$stop->loc->eva,
			sched_arr => defined $stop->{sched_arr} ? $stop->{sched_arr}->epoch : JSON::null,
			sched_dep => defined $stop->{sched_dep} ? $stop->{sched_dep}->epoch : JSON::null,
			rt_arr => defined $stop->{rt_arr} ? $stop->{rt_arr}->epoch : JSON::null,
			rt_dep => defined $stop->{rt_dep} ? $stop->{rt_dep}->epoch : JSON::null,
		});
		my @ret;
		foreach my $message ($stop->messages) {
			push(@ret, {
				short=>$message->short,
				text=>$message->text,
				code=>$message->code,
				type=>$message->type,
			});
		}
		@stop_messages{$stop->loc->eva} = [@ret];
	}
	print encode_json({
		id=>$status->id,
		operator=>$status->operator,
		direction=>$status->direction,
		no=>$status->number,
		polyline=>[@polyline],
		beeline=>$only_eva,
		route=>[@route],
		messages=>[@messages],
		stop_messages=>{%stop_messages}
	});
} else {
	print encode_json({
		error_code => $result->errcode,
		error_string => $result->errstr
	});
}
