#!/usr/bin/env perl

use strict;
use warnings;

use JSON;
use Travel::Status::DE::HAFAS;
use Travel::Status::DE::DBRIS;
use Travel::Status::MOTIS;
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
