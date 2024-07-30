#!/usr/bin/env perl

use strict;
use warnings;

use JSON;
use Travel::Status::DE::HAFAS;


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
	my %stop_messages;
	foreach my $stop ($status->route) {
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
		polyline=>[@polyline],
		beeline=>$only_eva,
		messages=>[@messages],
		stop_messages=>{%stop_messages}
	});
} else {
	print encode_json({
		error_code => $result->errcode,
		error_string => $result->errstr
	});
}
