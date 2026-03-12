#!/usr/bin/env perl

use strict;
use warnings;

use JSON;
use Travel::Status::DE::HAFAS;
use Travel::Status::DE::DBRIS;
use Travel::Status::MOTIS;
use Travel::Status::DE::EFA;
use DateTime;

sub  trim { my $s = shift; $s =~ s/^\s+|\s+$//g; return $s };

my $dt = DateTime->now(time_zone=>'Europe/Berlin');
if ($ARGV[2]) {
	$dt = DateTime->from_epoch(epoch=>$ARGV[2], time_zone=>'Europe/Berlin');
}

if ($ARGV[0] eq 'DBRIS') {
	my @no_train_number_types = qw(Bus RNV S STB STR U);
	my $ris = Travel::Status::DE::DBRIS->new(
		station => {
			eva => $ARGV[1],
			id => '@L=' . $ARGV[1] . '@' # ????? what did they mean by this
		},
		datetime => $dt
	);
	if (my @results = $ris->results) {
		my @trains;
		for my $train (@results) {
			my $dict = {
				id => $train->id,
				type => $train->type,
				line => $train->maybe_line_no,
				number => $train->maybe_train_no,
				direction => $train->destination,
				station => $train->stop_eva,
				scheduled => $train->sched_dep->epoch,
				realtime => defined $train->rt_dep ? $train->rt_dep->epoch : JSON::null,
				delay => $train->delay
			};
			if ($dict->{line} eq $dict->{number}) {
				if ($dict->{type} ~~ @no_train_number_types) {
					$dict->{number} = JSON::null;
				} else {
					$dict->{line} = JSON::null;
				}
			}
			push(@trains, $dict);
		}
		print encode_json({
			trains=>[@trains]
		});
	} else {
		print encode_json({
			error_string => $ris->errstr
		});
	}
	exit 0;
}
if ($ARGV[0] =~ /^MOTIS-/) {
	my $service = substr($ARGV[0],6);
	my $motis = Travel::Status::MOTIS->new(
		service => $service,
		stop_id => $ARGV[1],
		timestamp => $dt
	);
	if (my @results = $motis->results) {
		my @trains;
		for my $train (@results) {
			push(@trains, {
				id=>$train->id,
				type=>$train->mode,
				line=>$train->route_name,
				number=>0,
				direction=>$train->headsign,
				station=>$train->stopover->stop->TO_JSON,
				scheduled=>$train->stopover->scheduled_departure->epoch,
				realtime=>$train->is_realtime,
				delay=>defined $train->is_realtime ? $train->stopover->departure_delay : JSON::null,
			});
		}
		print encode_json({
			trains=>[@trains]
		});
	} else {
		print encode_json({
			error_code => 'motis broke rip',
			error_string => $motis->errstr
		});
	}
}
if ($ARGV[0] =~ /^EFA-/) {
	my $service = substr($ARGV[0],4);
	my $efa = Travel::Status::DE::EFA->new(
		service => $service,
		name => $ARGV[1],
		type => 'stopID',
		datetime => $dt
	);
	if (my @results = $efa->results) {
		my @trains;
		for my $train (@results) {
			push(@trains, {
				id=>$train->id,
				type=>defined $train->train_type ? $train->train_type : $train->mot_name,
				line=>$train->line,
				number=>defined $train->train_no ? $train->train_no : 0,
				direction=>$train->destination,
				station=>$ARGV[1],
				scheduled=>$train->sched_datetime->epoch,
				realtime=>defined $train->delay ? JSON::true : JSON::false,
				delay=>defined $train->delay ? $train->delay + 0 : JSON::null,
			});
		}
		print encode_json({
			trains=>[@trains]
		});
	} else {
		print encode_json({
			error_code => 'efa broke rip',
			error_string => $efa->errstr
		});
	}
} else {
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
}
