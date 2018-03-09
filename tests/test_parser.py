from xonotic_exporter.xonotic import XonoticMetricsParser, IllegalState
import pytest


VALID_RCON_RESPONSE1 = [
    b'"sv_public" is "1" ["1"]\n'
    b'host:     [\xe5\x8a\x9b] TheRegulars Instagib Server [git]\n'
    b'version:  Xonotic build 01:31:45 Apr 17 2017 - (gamename Xonotic)\n'
    b'protocol: 3504 (DP7)\n'
    b'map:      dissocia\n'
    b'timing:   30.4% CPU, 0.00% lost, offset avg 0.1ms, '
    b'max 1.6ms, sdev 0.2ms\n'
    b'players:  15 active (20 max)\n\n'
    b'^2IP                                             '
    b'%pl ping  time   frags  no   name\n'
    b'^3127.0.0.1:38839                               0  100  0:24:40    0  #1'
    b'   ^7^x0ffO^x3ffn^x6EFe^x9ffP^xcffa^xffft^xfcfc^xf9fh^xf6fM^xf3fa'
    b'^xf0fn^7\n'
    b'^7127.0.0.1:53131                              0   42  0:35:56 '
    b'-666  #2   ^7^x700\xd9\xad ^xF83\xe3\x82\xab ^x700\xd9\xad  '
    b'^x300\xc5\x9e\xd1\x92\xc7\xbb\xe2\x88\x82\xce\xbf\xcf\x89^x700'
    b'\xd1\xa2^x300\xc4\x99\xc7\xbb\xc5\x9f\xc5\xa7^7 \n'
    b'^3127.0.0.1:53491                              0  150  0:20:41 -666  '
    b'#3   ^7^x444Baud Modem^7\n'
    b'^7127.0.0.1:8149                              0   58  1:07:47   10  #4 '
    b'  ^7^7Wind[^x801\xe2\x96\xb2^xBB0\xe2\x9d\x8c^x069\xf0\x9f\x8c'
    b'\x8d^x777^xBBB]^7\n'
    b'^3127.0.0.1:53927                               0   58  0:04:19 -666  #5'
    b'   ^7\xf0\x9f\x98\xb2\n'
    b'^7127.0.0.1:53169                              0  174  1:02:13   '
    b'-1  #6   ^7^x700\xe2\x9a\xa1Umnum^x500zaan^7\n'
    b'^3127.0.0.1:34507                               0   87  0:12:00 -666  #8'
    b'   ^7david\n'
    b'^7127.0.0.1:62576                              0   58  0:34:55 -666  #9'
    b'   ^7^x002EAC ^xF00\xc2\xb7 ^x222B^xF8A( . )( . )^x222b^xF00i^x444ni^7\n'
    b'^3127.0.0.1:48999                              0   65  0:51:24   22  #10'
    b'  ^7^xEFD\xf0',
    b'\x9f\x98\xae^7\n^7127.0.0.1:54472                                0   48 '
    b' 0:09:57   -3  #11  ^7Shorty\n^3127.0.0.1:55441                        '
    b'      0   41  0:09:55   10  #12  ^7Gur^x0B3c^xFFFke^7\n^7127.0.0.1:48620'
    b'                                0   58  0:42:14    3  #13  ^7^2M^3o^7u'
    b'^3s^2e^7\n^3127.0.0.1:63314                             0  102  0:09:38 '
    b'  -1  #14  ^7^xE10Love^xE2FSex^xBD0Natursekt\xe2\x9d\x87^7\n'
    b'^7127.0.0.1:571                                0   55  0:06:45    0  #15'
    b'  ^7^xF00\xee\x83\xa7^xF80\xee\x83\xa9^xFE0\xee\x82\xb0^x8E0\xee\x83\xb6'
    b'^x0EB\xee\x83\xa1^x05E\xee\x83\xae^xD0F\xee\x83\xae^xF19\xee\x83\xa9'
    b'^xF05 \xee\x83\xb0^xF12\xee\x83\xa1\xee\x83\xb3^xE60\xee\x83\xa3^xFA0'
    b'\xee\x83\xaf^xED0\xee\x83\xac^xBF0\xee\x83\xa9^7\n^3127.0.0.1:44195   '
    b'                          0   72  0:02:01   27  #16  ^7^x555VampyDTG^7\n'
]


VALID_RCON_RESPONSE2 = [
    b'"sv_public" is "-1" ["1"]\n'
    b'host:     [\xe5\x8a\x9b] TheRegulars - Mars \xe2\x98\xa0 [git]\n'
    b'version:  Xonotic build 01:31:45 Apr 17 2017 - (gamename Xonotic)\n'
    b'protocol: 3504 (DP7)\n'
    b'map:      xonwall\n'
    b'timing:   3.0% CPU, 0.00% lost, offset avg 0.2ms, max 2.0ms, '
    b'sdev 0.2ms\n'
    b'players:  0 active (8 max)\n\n'
    b'^2IP                                             '
    b'%pl ping  time   frags  no   name\n'
]


VALID_RCON_RESPONSE3 = [
    b'"sv_public" is "1" ["1"]\n'
    b'host:     quake\n'
    b'version:  Xonotic build 13:26:57 Apr  1 2017 -'
    b' release (gamename Xonotic)\n'
    b'protocol: 3504 (DP7)\n'
    b'map:      hrewtymp1_q3\n'
    b'timing:   13.5% CPU, 0.00% lost, offset avg 0.1ms, max 0.2ms,'
    b' sdev 0.0ms\n'
    b'players:  5 active (20 max)\n\n'
    b'^2IP                                             %pl'
    b' ping  time   frags  no   name\n^'
    b'3127.0.0.1:15394                             0   33  0:00:20 -666  #1'
    b'   ^7test\n^7botclient                                        '
    b'0    0  0:00:12    0  #2   ^7{bot} Anyuta\n^3botclient               '
    b'                         0    0  0:00:12    0  #3   ^7{bot}'
    b' Octavia\n^7botclient                                        0    '
    b'0  0:00:12    0  #4   ^7{bot} Albert\n^3botclient                 '
    b'                       0    0  0:00:12    0  #5   ^7{bot} Luiz\n'
]


INVALID_RCON_RESPONSE = [
    VALID_RCON_RESPONSE1[1],
    VALID_RCON_RESPONSE1[0],
]


@pytest.fixture(scope="function")
def parser():
    return XonoticMetricsParser()


def test_valid_multiple(parser):
    for data in VALID_RCON_RESPONSE1:
        parser.feed_data(data)

    assert parser.metrics['sv_public'] == 1
    assert parser.metrics['map'] == 'dissocia'
    assert parser.metrics['players_count'] == 15
    assert parser.done is True


def test_invalid_multiple(parser):
    with pytest.raises(IllegalState):
        for data in INVALID_RCON_RESPONSE:
            parser.feed_data(data)


def test_valid_simple(parser):
    for data in VALID_RCON_RESPONSE2:
        parser.feed_data(data)

    assert parser.metrics['sv_public'] == -1
    assert parser.metrics['map'] == 'xonwall'
    assert parser.metrics['players_count'] == 0
    assert parser.metrics['timing_cpu'] == pytest.approx(3.0, 0.1)
    assert parser.done is True


def test_parser_with_bots(parser):
    for data in VALID_RCON_RESPONSE3:
        parser.feed_data(data)

    assert parser.metrics['sv_public'] == 1
    assert parser.metrics['players_count'] == 5
    assert parser.metrics['players_active'] == 0
    assert parser.metrics['players_spectators'] == 1
    assert parser.metrics['players_bots'] == 4
