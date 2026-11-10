# ArduPilot ChibiOS and PX4 Hardware Board Registry
# Source: Tools/AP_Bootloader/board_types.txt
import re
import os
import glob
import time

BOARD_ID_MAP = {
    3: "EXT_HW_RADIOLINK_MINI_PIX",
    5: "TARGET_HW_PX4_FMU_V1",
    6: "TARGET_HW_PX4_FLOW_V1",
    9: "TARGET_HW_CUBE_F4",
    10: "TARGET_HW_PX4_PIO_V2",
    11: "TARGET_HW_PX4_FMU_V4",
    12: "TARGET_HW_CRAZYFLIE",
    13: "TARGET_HW_PX4_PIO_V3",
    14: "TARGET_HW_CRAZYFLIE21",
    20: "AP_HW_F4BY",
    28: "TARGET_HW_FMUK66_V3",
    29: "TARGET_HW_AV_X_V1",
    30: "TARGET_HW_FMUK66_E",
    31: "TARGET_HW_FMURT1062-V1",
    32: "TARGET_HW_SMARTAP_PRO",
    33: "TARGET_HW_AUAV_X2V1",
    42: "TARGET_HW_OMNIBUSF4SD",
    50: "TARGET_HW_PX4_FMU_V5",
    51: "TARGET_HW_PX4_FMU_V5X",
    52: "TARGET_HW_PX4_FMU_V6",
    53: "TARGET_HW_PX4_FMU_V6X",
    54: "TARGET_HW_PX4_FMU_V6",
    55: "TARGET_HW_SMARTAP_AIRLINK",
    56: "TARGET_HW_PX4_FMU_V6C",
    57: "TARGET_HW_ARK_FMU_V6X",
    58: "TARGET_HW_ARK_PI6X",
    59: "TARGET_HW_ARK_FPV",
    61: "TARGET_HW_ARK_FMU_V6S",
    64: "TARGET_HW_TAP_V1",
    65: "TARGET_HW_AEROFC_V1",
    66: "TARGET_TAP_V2",
    78: "TARGET_HW_HOLYBRO_PIX32_V5",
    79: "TARGET_HW_HOLYBRO_CAN_GPS",
    80: "TARGET_HW_ARK_CAN_FLOW",
    81: "TARGET_HW_ARK_CAN_GPS",
    82: "TARGET_HW_ARK_CAN_RTK_GPS",
    83: "TARGET_HW_ARK_CANNODE",
    85: "TARGET_HW_FF_RTK_CAN_GPS",
    86: "TARGET_HW_PDW_MAS_MAIN-V1",
    88: "TARGET_HW_MINDPX_V2",
    89: "TARGET_HW_ARK_X20_GPS",
    97: "TARGET_HW_ATL_MANTIS_EDU",
    98: "TARGET_HW_PX4_AEROCORE_V1",
    99: "TARGET_HW_PX4_DISCOVERY_V1",
    110: "TARGET_HW_SYRO_V6X",
    120: "AP_HW_CUBEYELLOW",
    121: "AP_HW_OMNIBUSF7V2",
    122: "AP_HW_KAKUTEF4",
    123: "TARGET_HW_KAKUTEF7",
    124: "AP_HW_REVOLUTION",
    125: "AP_HW_MATEKF405",
    126: "AP_HW_NUCLEOF767ZI",
    127: "AP_HW_MATEKF405_WING",
    128: "AP_HW_AIRBOTF4",
    130: "AP_HW_SPARKYV2",
    131: "AP_HW_OMNIBUSF4PRO",
    132: "AP_HW_ANYFCF7",
    133: "AP_HW_OMNIBUSNANOV6",
    134: "AP_HW_SPEEDYBEEF4",
    135: "AP_HW_F35LIGHTNING",
    136: "AP_HW_MRO_X2V1_777",
    137: "AP_HW_OMNIBUSF4V6",
    138: "AP_HW_HELIOSPRING",
    139: "AP_HW_DURANDAL",
    140: "AP_HW_CUBEORANGE",
    141: "AP_HW_MRO_CONTROL_ZERO",
    142: "AP_HW_MRO_CONTROL_ZERO_OEM",
    143: "AP_HW_MATEKF765_WING",
    144: "AP_HW_JDMINIF405",
    145: "AP_HW_KAKUTEF7_MINI",
    146: "AP_HW_H757I_EVAL",
    188: "AP_HW_MAZZYSTARDRONE",
    212: "TARGET_HW_THE_PEACH_K1",
    213: "TARGET_HW_THE_PEACH_R1",
    1000: "AP_HW_F103_PERIPH",
    1001: "AP_HW_CUAV_GPS",
    1002: "AP_HW_OMNIBUSF4",
    1003: "AP_HW_CUBEBLACKPLUS",
    1004: "AP_HW_F303_PERIPH",
    1005: "AP_HW_ZUBAXGNSS",
    1006: "AP_HW_NIGHTCRAWLER",
    1007: "AP_HW_SKYBOT",
    1008: "AP_HW_FRSKY_R9",
    1009: "AP_HW_CUAV_NORA",
    1010: "AP_HW_CUAV_X7_PRO",
    1011: "AP_HW_SUCCEXF4",
    1012: "AP_HW_LIGHTSPARKMINI",
    1013: "AP_HW_MATEKH743",
    1014: "AP_HW_MATEKF405_GPS",
    1015: "AP_HW_MRO_NEXUS",
    1016: "AP_HW_HITEC_MOSAIC",
    1017: "AP_HW_MRO_PIXRACER_PRO",
    1018: "AP_HW_TWD_H7",
    1019: "AP_HW_MAMBA405",
    1020: "AP_HW_H31_PIXC4",
    1021: "AP_HW_QioTekZealotF427",
    1022: "AP_HW_MRO_CTRL_ZERO_CLASSIC",
    1023: "AP_HW_MRO_CTRL_ZERO_H7",
    1024: "AP_HW_MRO_CTRL_ZERO_OEM_H7",
    1025: "AP_HW_BEASTH7",
    1026: "AP_HW_BEASTF7",
    1027: "AP_HW_FlywooF745",
    1028: "AP_HW_FreeflyRTK",
    1029: "AP_HW_luminousbee5",
    1030: "AP_HW_KAKUTEF4_MINI",
    1031: "AP_HW_H31_PIXC4_PI",
    1032: "AP_HW_H31_PIXC4_JETSON",
    1033: "AP_HW_CUBEORANGE_JOEY",
    1034: "AP_HW_SierraF9P",
    1035: "AP_HW_HolybroGPS",
    1036: "AP_HW_QioTekZealotH743",
    1037: "AP_HW_HEREPRO",
    1038: "AP_HW_MAMBABASICF4",
    1039: "AP_HW_ARGOSDYNE_DP1000",
    1040: "AP_HW_Nucleo491",
    1041: "AP_HW_mRoM10095",
    1042: "AP_HW_FlywooF745Nano",
    1043: "AP_HW_HERE3PLUS",
    1044: "AP_HW_BirdCANdy",
    1045: "AP_HW_SKYSTARSF405DJI",
    1046: "AP_HW_HITEC_AIRSPEED",
    1047: "AP_HW_NucleoL496",
    1048: "AP_HW_KakuteH7",
    1049: "AP_HW_ICSI_Kestrel",
    1050: "AP_HW_SierraL431",
    1051: "AP_HW_NucleoL476",
    1052: "AP_HW_SierraF405",
    1053: "AP_HW_HolybroG4_GPS",
    1054: "AP_HW_MatekF405_TE",
    1055: "AP_HW_SierraF412",
    1056: "AP_HW_BEASTH7v2",
    1057: "AP_HW_BEASTF7v2",
    1058: "AP_HW_KakuteH7Mini",
    1059: "AP_HW_JHEMCUGSF405A",
    1060: "AP_HW_SPRACINGH7",
    1061: "AP_HW_DEVEBOXH7",
    1062: "AP_HW_MatekL431",
    1063: "AP_HW_CUBEORANGEPLUS",
    1064: "AP_HW_CarbonixF405",
    1065: "AP_HW_QioTekAdeptF407",
    1066: "AP_HW_QioTekAdeptF427",
    1067: "AP_HW_FlyingMoonF407",
    1068: "AP_HW_FlyingMoonF427",
    1069: "AP_HW_CUBERED_PRIMARY",
    1070: "AP_HW_CUBERED_SECONDARY",
    1071: "AP_HW_GreenSight_UltraBlue",
    1072: "AP_HW_GreenSight_microBlue",
    1073: "AP_HW_MAMBAH743_V4",
    1074: "AP_HW_REAPERF745_V2",
    1075: "AP_HW_SKYSTARSH7HD",
    1076: "AP_HW_PixSurveyA1",
    1077: "AP_HW_AEROFOX_AIRSPEED",
    1078: "AP_HW_ATOMRCF405",
    1079: "AP_HW_CUBENODE",
    1080: "AP_HW_AEROFOX_PMU",
    1081: "AP_HW_JHEMCUGF16F405",
    1082: "AP_HW_SPEEDYBEEF4V3",
    1083: "AP_HW_PixPilot-V6",
    1084: "AP_HW_JFB100",
    1085: "AP_HW_C_RTK2_HP",
    1086: "AP_HW_JUMPER_XIAKE800",
    1087: "AP_HW_Sierra_F1",
    1088: "AP_HW_HolybroCompass",
    1089: "AP_HW_FOXEERH743_V1",
    1090: "AP_HW_PixFlamingoL4R5_V1",
    1091: "AP_HW_Sierra-TrueNavPro",
    1092: "AP_HW_Sierra-TrueNav",
    1093: "AP_HW_Sierra-TrueNorth",
    1094: "AP_HW_Sierra-TrueSpeed",
    1095: "AP_HW_Sierra-PrecisionPoint",
    1096: "AP_HW_PixPilot-V3",
    1097: "AP_HW_PixSurveyA2",
    1098: "AP_HW_mRoCANPWM",
    1099: "AP_HW_FlywooF405S_AIO",
    1100: "AP_HW_mRoCANPower",
    1101: "AP_HW_mRoControlOne",
    1102: "AP_HW_rFCU",
    1103: "AP_HW_rGNSS",
    1104: "AP_HW_AEROFOX_AIRSPEED_DLVR",
    1105: "AP_HW_KakuteH7-Wing",
    1106: "AP_HW_SpeedyBeeF405WING",
    1107: "AP_HW_PixSurveyA-IND",
    1108: "AP_HW_SPRACINGH7RF",
    1109: "AP_HW_AEROFOX_GNSS_F9P",
    1110: "AP_HW_JFB110",
    1111: "AP_HW_SDMODELH7V1",
    1112: "AP_HW_FlyingMoonH743",
    1113: "AP_HW_YJUAV_A6",
    1114: "AP_HW_YJUAV_A6Nano",
    1115: "AP_HW_ACNS_CM4PILOT",
    1116: "AP_HW_ACNS_F405AIO",
    1117: "AP_HW_BLITZF7AIO",
    1118: "AP_HW_RADIX2HD",
    1119: "AP_HW_HEEWING_F405",
    1120: "AP_HW_PodmanH7",
    1121: "AP_HW_mRo-M10053",
    1122: "AP_HW_mRo-M10044",
    1123: "AP_HW_SIYI_N7",
    1124: "AP_HW_mRoCZOEM_revG",
    1125: "AP_HW_BETAFPV_F405",
    1126: "AP_HW_QioTekAdeptH743",
    1127: "AP_HW_YJUAV_A6SE",
    1128: "AP_HW_QioTekAdept_6C",
    1129: "AP_HW_PixFlamingoL4R5_V2",
    1130: "AP_HW_PixFlamingoF427_V1",
    1131: "AP_HW_PixFlamingoF767_V1",
    1132: "AP_HW_PixFlamingoH743I",
    1133: "AP_HW_PixFlamingoH743V",
    1134: "AP_HW_AR-F407SmartBat",
    1135: "AP_HW_SPEEDYBEEF4MINI",
    1136: "AP_HW_SPEEDYBEEF4V4",
    1137: "AP_HW_FlywooF405Pro",
    1138: "AP_HW_TMOTORH7",
    1139: "AP_HW_MICOAIR405",
    1140: "AP_HW_PixPilot-C3",
    1141: "AP_HW_YJUAV_A6SE_H743",
    1142: "AP_HW_FSO_POWER_STACK",
    1143: "AP_HW_ATOMRCF405NAVI_DLX",
    1144: "AP_HW_YJUAV_A6Ultra",
    1145: "AP_HW_TULIP_BATTMON",
    1146: "AP_HW_AnyleafH7",
    1147: "AP_HW_mRoKitCANrevC",
    1148: "AP_HW_BotBloxSwitch",
    1149: "AP_HW_MatekH7A3",
    1150: "AP_HW_MicoAir405v2",
    1151: "AP_HW_VRBRAIN_V51",
    1152: "AP_HW_VRBRAIN_V52",
    1154: "AP_HW_VRBRAIN_V54",
    1155: "AP_HW_ORQAF405PRO",
    1156: "AP_HW_CBU_StampH743",
    1157: "AP_HW_FOXEERF405_V2",
    1158: "AP_HW_CSKY405",
    1159: "AP_HW_NxtPX4v2",
    1160: "AP_HW_PixPilot-V6PRO",
    1161: "AP_HW_MicoAir405Mini",
    1162: "AP_HW_BlitzH7Pro",
    1163: "AP_HW_BlitzF7Mini",
    1164: "AP_HW_BlitzF7",
    1165: "AP_HW_3DR-ASAUAV",
    1166: "AP_HW_MicoAir743",
    1167: "AP_HW_SDMODELH7V2",
    1168: "AP_HW_BlitzH7Wing",
    1169: "AP_HW_JHEMCUF405WING",
    1170: "AP_HW_MatekG474",
    1171: "AP_HW_PhenixH7_lite",
    1172: "AP_HW_PhenixH7_Pro",
    1173: "AP_HW_2RAWH743",
    1174: "AP_HW_X-MAV-AP-H743V2",
    1175: "AP_HW_BETAFPV_F4_2-3S_20A",
    1176: "AP_HW_MicoAir743-AIO",
    1177: "AP_HW_CrazyF405",
    1179: "AP_HW_MicoAir743v2",
    1180: "AP_HW_FlywooF405HD_AIOv2",
    1181: "AP_HW_FlywooH743Pro",
    1182: "AP_HW_CBU_StampH743_LC",
    1183: "AP_HW_NarinH7",
    1184: "AP_HW_BrahmaF4",
    1185: "AP_HW_X-MAV-AP-H743Lite",
    1186: "AP_HW_3DRControlN1",
    1187: "AP_HW_CORVON405V2_1",
    1188: "AP_HW_NarinH5",
    1189: "AP_HW_CORVON743V1",
    1190: "AP_HW_DAKEFPVF405",
    1191: "AP_HW_ORBITH743",
    1192: "AP_HW_TMOTOR-PACER-H743",
    1193: "AP_HW_DAKEFPVH743",
    1194: "AP_HW_DAKEFPVH743PRO",
    1195: "AP_HW_SEQUREH743",
    1196: "AP_HW_SPEDIXH743",
    1197: "AP_HW_SPEDIXF405",
    1198: "AP_HW_AEDROXH7",
    1199: "AP_HW_NarinX3",
    1200: "AP_HW_JFB200",
    1201: "AP_HW_SKYSTARSF405V2",
    1202: "AP_HW_MicoAir743-Lite",
    1203: "AP_HW_X-MAV-AP-H743R1",
    1204: "AP_HW_ORQAH7QUADCORE",
    1205: "AP_HW_ESP32_PERIPH",
    1206: "AP_HW_ESP32S3_PERIPH",
    1207: "AP_HW_NUCLEO_H753ZI",
    1208: "AP_HW_DAKEFPVH743_SLIM",
    1209: "AP_HW_AIRBRAIN_H743",
    1210: "AP_HW_Morakot",
    1211: "AP_HW_CORVON_V5",
    1212: "AP_HW_CSKY_PMU",
    1213: "AP_HW_PilotGaeaSH7V1",
    1214: "AP_HW_JPilot-C",
    1215: "AP_HW_SIYI-UniFC-6-PICO",
    1216: "AP_HW_CSKY_AVEGA6X",
    1217: "AP_HW_CSKY_AVEGALITER03",
    1218: "AP_HW_AMOV_FLYCORE",
    1219: "AP_HW_ORBITH743v2",
    1220: "AP_HW_X-MAV-AP-H743V3",
    1221: "AP_HW_SIMPLIFLYH7",
    1222: "AP_HW_MUPilot",
    1223: "AP_HW_HWH7",
    1224: "AP_HW_BrahmaH7",
    1225: "AP_HW_TUSTIN_MACH",
    1226: "AP_HW_FlyFishRCF405",
    1227: "AP_HW_ATLAS_CONTROL",
    1228: "AP_HW_MatekH7A3_Wing",
    1229: "AP_HW_CORVON743V2",
    1230: "AP_HW_CORVON_V6",
    1233: "AP_HW_YARIV6S",
    1234: "AP_HW_YARIV6X",
    1235: "AP_HW_YARI_GNSS",
    1236: "AP_HW_YARI_RTK_GNSS",
    1242: "AP_HW_FLYINGRCH7DPRO",
    1248: "AP_HW_PRINCIPIOT_H7PI",
    1250: "AP_HW_KT_FMU_F1",
    1251: "AP_HW_SIMPLIFLY_NEO",
    1275: "AP_HW_GPILOT_P1",
    1299: "AP_HW_MicoAir743v3",
    1300: "AP_HW_SKYDROID-S3",
    1301: "AP_HW_CBUnmanned-CM405-FC",
    1302: "AP_HW_CBU_H753-SOM",
    1315: "AP_HW_KHA_ETH",
    1316: "AP_HW_SAAMPIXV1_1",
    1320: "AP_HW_SkyroninL431",
    1330: "AP_HW_NYXTRONICS_NYX405V1",
    1351: "AP_HW_VRUBRAIN_V51",
    1361: "AP_HW_FlysparkF4",
    1362: "AP_HW_SPARKNAVI_BLUE",
    1363: "AP_HW_SPARKNAVI_BLUEv2",
    1364: "AP_HW_SPARKNAVI_F405",
    1365: "AP_HW_SPARKNAVI_H743_R45",
    1366: "AP_HW_SPARKNAVI_ETH",
    1380: "AP_HW_Kao1",
    1400: "AP_HW_CUBEORANGE_PERIPH",
    1401: "AP_HW_CUBEBLACK_PERIPH",
    1402: "AP_HW_PIXRACER_PERIPH",
    1403: "AP_HW_SWBOOMBOARD_PERIPH",
    1404: "AP_HW_VIMDRONES_FLOW",
    1405: "AP_HW_VIMDRONES_MOSAIC_X5",
    1406: "AP_HW_VIMDRONES_MOSAIC_H",
    1407: "AP_HW_VIMDRONES_PERIPH",
    1408: "AP_HW_PIXHAWK6X_PERIPH",
    1409: "AP_HW_CUBERED_PERIPH",
    1410: "AP_HW_RadiolinkPIX6",
    1411: "AP_HW_JHEMCU-H743HD",
    1412: "AP_HW_JHEMCUF405PRO",
    1413: "AP_HW_DCD_FC",
    1415: "AP_HW_TRITIUM_EAH743",
    1417: "AP_HW_RadiolinkF405",
    1422: "AP_HW_LongbowF405",
    1445: "AP_HW_ResoluteH7",
    1500: "AP_HW_StellarF4",
    1501: "AP_HW_GEPRCF745BTHD",
    1502: "AP_HW_GEPRC_TAKER_H743",
    1503: "AP_HW_StellarH7V2",
    1504: "AP_HW_StellarF4V2",
    1511: "AP_HW_BCUBEF745V2",
    1524: "AP_HW_HGLRCF405V4",
    1525: "AP_HW_HGLRC_H743_EVO",
    1526: "AP_HW_HGLRC_H743_PRO",
    1530: "AP_HW_F4BY_F427",
    1531: "AP_HW_F4BY_H743",
    1800: "AP_HW_AERIUM_RADIAN_F405",
    1801: "AP_HW_AERIUM_RADIAN_H743",
    1850: "AP_HW_A2M6X",
    1855: "AP_HW_A2M6X_NANO",
    1860: "AP_HW_A2M6X_V2",
    1910: "AP_HW_VRCORE_V10",
    1930: "AP_HW_AGAM_GNSS-CAN",
    1931: "AP_HW_AGAM_GNSSPLUS",
    1932: "AP_HW_AGAM_BASE-RTK",
    1933: "AP_HW_AGAM_CAN-RTK",
    1939: "AP_HW_AGAM_FloRange",
    1940: "AP_HW_AGAM_MegH7",
    1949: "AP_HW_AGAM_v6XRT",
    1950: "AP_HW_HCR-504",
    1951: "AP_HW_HCR-506",
    1952: "AP_HW_HCR-507",
    1953: "AP_HW_HCR-511",
    1954: "AP_HW_HCR-512",
    1955: "AP_HW_HCR-516",
    1956: "AP_HW_HCR-518",
    1957: "AP_HW_HCR-523",
    1958: "AP_HW_HCR-533",
    1959: "AP_HW_HCR-536",
    1960: "AP_HW_HCR-551",
    1961: "AP_HW_HCR-565",
    1962: "AP_HW_HCR-566",
    1963: "AP_HW_CORVON_G1",
    1964: "AP_HW_CORVON_G2",
    2000: "AP_HW_MFT-SEMA100",
    2005: "AP_HW_SULILGH7-P1-P2",
    2024: "AP_HW_AET-H743-Basic",
    2501: "AP_HW_BOTWINGF405",
    2509: "AP_HW_AET-H743-AIR",
    2510: "AP_HW_AET-U7",
    2511: "AP_HW_AET-AT405A",
    2512: "AP_HW_AET-405-Mini",
    2513: "AP_HW_INDIH743",
    2714: "AP_HW_SakuraRC-H743",
    2815: "AP_HW_SkyRukh_Surge_H7",
    3141: "AP_HW_MADPILOT_H7",
    4000: "AP_HW_KRSHKF7_MINI",
    4002: "AP_HW_KARSHAKH743VTOL",
    4100: "AP_HW_AIUAV_PlatFly_H7",
    4200: "AP_HW_HAKRC_F405",
    4201: "AP_HW_HAKRC_F405Wing",
    4203: "AP_HW_HAKRC_H743",
    4300: "AP_HW_AeroCogito-H7Digital",
    4500: "AP_HW_LUMENIER_LUX_F765_NDAA",
    4501: "AP_HW_LUMENIER_LUX_H743_NDAA",
    5200: "AP_HW_AIRVOLUTE_DCS2",
    5210: "AP_HW_AOCODA-RC-H743DUAL",
    5211: "AP_HW_AOCODA-RC-F405V3",
    5220: "AP_HW_UAV-DEV-HAT-H7",
    5221: "AP_HW_UAV-DEV-NucPilot-H7",
    5222: "AP_HW_UAV-DEV-M10S-L4",
    5223: "AP_HW_UAV-DEV-F9P-G4",
    5224: "AP_HW_UAV-DEV-UM982-G4",
    5225: "AP_HW_UAV-DEV-M20D-G4",
    5226: "AP_HW_UAV-DEV-Sensorboard-G4",
    5227: "AP_HW_UAV-DEV-PWM-G4",
    5228: "AP_HW_UAV-DEV-AUAV-H7",
    5229: "AP_HW_UAV-DEV-FC-H7",
    5230: "AP_HW_UAV-DEV-FC-UM982-H7",
    5231: "AP_HW_UAV-DEV-FC-M10S-H7",
    5232: "AP_HW_UAV-DEV-UM982-H7",
    5233: "AP_HW_UAV-DEV-PM-G4",
    5234: "AP_HW_UAV-DEV-AUAV-G4",
    5235: "AP_HW_UAV-DEV-ETHERNET-H7",
    5236: "AP_HW_UAV-DEV-FC-PIZERO-H7",
    5237: "AP_HW_UAV-DEV-M10S-G4",
    5240: "AP_HW_TM-SYS-BeastFC",
    5241: "AP_HW_TM-SYS-Sensornode",
    5242: "AP_HW_TM-SYS-OpenHDFPV",
    5243: "AP_HW_TM-SYS-VisualNAV",
    5244: "AP_HW_TM-SYS-Airspeed",
    5250: "AP_HW_TBS_LUCID_H7",
    5251: "AP_HW_TBS_LUCID_PRO",
    5252: "AP_HW_TBS_L431_PERIPH",
    5253: "AP_HW_TBS_LUCID_H7_WING",
    5254: "AP_HW_TBS_LUCID_H7_WING_AIO",
    5255: "AP_HW_TBS_LUCID_H7_OEM",
    5256: "AP_HW_TBS_LUCID_H7V3",
    5270: "AP_HW_SpeedyBeeF405WINGV2",
    5271: "AP_HW_SpeedyBeeF405AIO",
    5272: "AP_HW_SpeedyBeeF4V5",
    5280: "AP_HW_Dynamix_PIXEL",
    5281: "AP_HW_Dynamix_PYRO",
    5301: "AP_HW_Sierra-TrueNavPro-G4",
    5302: "AP_HW_Sierra-TrueNavIC",
    5303: "AP_HW_Sierra-TrueNorth-G4",
    5304: "AP_HW_Sierra-TrueSpeed-G4",
    5305: "AP_HW_Sierra-PrecisionPoint-G4",
    5306: "AP_HW_Sierra-AeroNex",
    5307: "AP_HW_Sierra-TrueFlow",
    5308: "AP_HW_Sierra-TrueNavIC-Pro",
    5309: "AP_HW_Sierra-F1-Pro",
    5401: "AP_HW_Holybro-PMU-F4",
    5402: "AP_HW_Holybro-UM982-G4",
    5403: "AP_HW_Holybro-UM960-H7",
    5404: "AP_HW_Holybro-PERIPH-H7",
    5405: "AP_HW_Holybro-DroneCAN-Airspeed",
    5406: "AP_HW_Holybro-KakuteF4-Wing",
    5501: "AP_HW_MATEKH743SE",
    5600: "AP_HW_ZeroOne_X6",
    5601: "AP_HW_ZeroOne_X9",
    5610: "AP_HW_ZeroOne_M9",
    5620: "AP_HW_ZeroOne_A3",
    5621: "AP_HW_ZeroOne_A6i",
    5700: "AP_HW_DroneBuild_G1",
    5701: "AP_HW_DroneBuild_G2",
    5711: "AP_HW_IOMCU_F103",
    5712: "AP_HW_IOMCU_F103_8MHZ",
    5713: "AP_HW_IOMCU_F100",
    5730: "AP_HW_NWBLUE_PROH757",
    5740: "AP_HW_ZenFC_H743",
    5800: "AP_HW_DroneerF405",
    5801: "AP_HW_DroneerX6",
    5810: "AP_HW_BrotherHobbyH743",
    5811: "AP_HW_BrotherHobbyF405v3",
    5820: "AP_HW_VIMDRONES_BMS",
    5830: "AP_HW_CyberX-v10",
    5831: "AP_HW_CyberX-Cube",
    5900: "AP_HW_NewBeeDrone_PixNova",
    5905: "AP_HW_NewBeeDrone_HUMMINGBIRD_FC305_H7",
    6000: "AP_HW_sw-spar-f407",
    6001: "AP_HW_sw-boom-f407",
    6002: "AP_HW_sw-nav-f405",
    6100: "AP_HW_MFE_PDB_CAN",
    6101: "AP_HW_MFE_POS3_CAN",
    6102: "AP_HW_MFE_RTK_CAN",
    6103: "AP_HW_MFE_AirSpeed_CAN",
    6104: "AP_HW_PixSurveyA2-IND",
    6110: "AP_HW_SVehicle-E2",
    6111: "AP_HW_SVehicle-E2-mini",
    6120: "AP_HW_PILOTIX",
    6130: "AP_HW_Saolah743",
    7000: "AP_HW_CUAV-7-NANO",
    7001: "AP_HW_CUAV-V6X-V2",
    7002: "AP_HW_CUAV-X25-EVO",
    7004: "AP_HW_CUAV-X25-MEGA",
    7100: "AP_HW_VUAV-V7pro",
    7101: "AP_HW_VUAV-TinyV7",
    7110: "AP_HW_AEROFOX_H7",
    7120: "AP_HW_Accton_Godwit_GA1",
    7121: "AP_HW_Accton_Godwit_GFF4",
    7122: "AP_HW_Accton_Godwit_GFH7",
    7130: "AP_HW_CoreWingF405WingV2",
    7131: "AP_HW_CoreWingF405WMiniV2",
    7140: "AP_HW_LECTRON_Pi5_H7",
    7150: "AP_HW_SED_FC_H753",
    7151: "AP_HW_SED_GPS",
    7152: "AP_HW_SED_AirSpeed",
    7153: "AP_HW_SED_UGNSS",
    7162: "AP_HW_Viima-WH7-v2",
    7163: "AP_HW_Viima-WH7-v3",
    7170: "AP_HW_TYKHO_TLS7V2",
    7171: "AP_HW_TYKHO_TLS7-Wing",
    7180: "AP_HW_RPI_UAVFC",
    7181: "AP_HW_RASPBERRYPI_PICO2",
    7182: "AP_HW_RASPBERRYPI_LAUREL",
    10053: "AP_HW_Pixhawk6_ODID",
    10140: "AP_HW_CubeOrange_ODID",
    11009: "AP_HW_CUAV_NORA_ODID",
    11010: "AP_HW_CUAV_X7_PRO_ODID",
    11063: "AP_HW_CUBEORANGEPLUS_ODID",
    11123: "AP_HW_SIYI_N7_ODID",
    11215: "AP_HW_SIYI-UniFC-6-PICO_ODID",
    11300: "AP_HW_SKYDROID-S3_ODID",
    12509: "AP_HW_AET-H743-AIR_ODID",
    12510: "AP_HW_AET-U7_ODID",
    12511: "AP_HW_AET-AT405A_ODID",
    12512: "AP_HW_AET-405-Mini_ODID",
    15600: "AP_HW_ZeroOne_X6_ODID",
    15601: "AP_HW_ZeroOne_X9_ODID",
    15610: "AP_HW_ZeroOne_M9_ODID",
    15620: "AP_HW_ZeroOne_A3_ODID",
    15621: "AP_HW_ZeroOne_A6i_ODID",
    17000: "AP_HW_CUAV-7-NANO_ODID",
    17001: "AP_HW_CUAV-V6X-V2_ODID",
    17002: "AP_HW_CUAV-X25-EVO_ODID",
    17004: "AP_HW_CUAV-X25-MEGA_ODID",
    41775: "TARGET_HW_MODALAI_FC_V1",
    41776: "TARGET_HW_MODALAI_FC_V2",
    41777: "TARGET_HW_MODALAI_VOXL2_IO",
}

def format_fc_board_name(raw_name):
    if not raw_name:
        return "Hardware FC"
    name = str(raw_name).strip()
    for prefix in ['AP_HW_', 'TARGET_HW_']:
        if name.startswith(prefix):
            name = name[len(prefix):]
    if re.search(r'\bSITL\b', name, re.IGNORECASE):
        return 'SITL'
    # SpeedyBee family
    m_sb = re.match(r'^SpeedyBee([A-Za-z0-9_\-]+)$', name, re.IGNORECASE)
    if m_sb:
        part = m_sb.group(1).replace('_', ' ').strip()
        part = re.sub(r'(?i)[_\-\s]*WING', '-WING', part)
        part = re.sub(r'([FfHhGg][0-9]{3})([A-Za-z]+)', r'\1 \2', part)
        return f"SpeedyBee {part.strip()}"
    # Matek family
    m_mat = re.match(r'^Matek([A-Za-z0-9_\-]+)$', name, re.IGNORECASE)
    if m_mat:
        part = m_mat.group(1).replace('_', ' ').strip()
        part = re.sub(r'(?i)[_\-\s]*WING', '-WING', part)
        part = re.sub(r'([FfHhGg][0-9]{3})([A-Za-z]+)', r'\1 \2', part)
        return f"Matek {part.strip()}"
    # Cube / CubePilot family
    m_cube = re.match(r'^Cube([A-Za-z0-9_\-]+)$', name, re.IGNORECASE)
    if m_cube:
        part = m_cube.group(1).replace('_', ' ').replace('PLUS', '+').strip().title()
        part = re.sub(r'\bF4\b', '(F4)', part)
        return f"Cube {part}"
    # Pixhawk family
    m_pix = re.match(r'^(?:PX4_FMU_|Pixhawk)([A-Za-z0-9_\-]+)$', name, re.IGNORECASE)
    if m_pix:
        part = m_pix.group(1).replace('_', ' ').strip()
        return f"Pixhawk {part.strip()}"
    # Kakute / Holybro family
    m_kak = re.match(r'^(?:Holybro_)?Kakute([A-Za-z0-9_\-]+)$', name, re.IGNORECASE)
    if m_kak:
        part = m_kak.group(1).replace('_', ' ').strip()
        part = re.sub(r'(?i)[_\-\s]*WING', '-WING', part)
        part = re.sub(r'([FfHhGg][0-9]{3})([A-Za-z]+)', r'\1 \2', part)
        return f"Kakute {part.strip()}"
    # Mamba / Diatone family
    m_mam = re.match(r'^(?:Diatone_)?Mamba([A-Za-z0-9_\-]+)$', name, re.IGNORECASE)
    if m_mam:
        part = m_mam.group(1).replace('_', ' ').strip()
        part = re.sub(r'(?i)[_\-\s]*WING', '-WING', part)
        part = re.sub(r'([FfHhGg][0-9]{3})([A-Za-z]+)', r'\1 \2', part)
        return f"Mamba {part.strip()}"
    # AtomRC family
    m_atom = re.match(r'^AtomRC([A-Za-z0-9_\-]+)$', name, re.IGNORECASE)
    if m_atom:
        part = m_atom.group(1).replace('_', ' ').strip()
        part = re.sub(r'(?i)[_\-\s]*WING', '-WING', part)
        part = re.sub(r'([FfHhGg][0-9]{3})([A-Za-z]+)', r'\1 \2', part)
        return f"AtomRC {part.strip()}"
    # Foxeer family
    m_fox = re.match(r'^Foxeer([A-Za-z0-9_\-]+)$', name, re.IGNORECASE)
    if m_fox:
        part = m_fox.group(1).replace('_', ' ').strip()
        part = re.sub(r'(?i)[_\-\s]*WING', '-WING', part)
        part = re.sub(r'([FfHhGg][0-9]{3})([A-Za-z]+)', r'\1 \2', part)
        return f"Foxeer {part.strip()}"
    return name.replace('_', ' ').strip()


USB_VID_PID_MAP = {
    (0x26AC, 0x0011): "Cube Black",
    (0x26AC, 0x0012): "Cube Orange",
    (0x26AC, 0x0016): "Cube Black+",
    (0x26AC, 0x0032): "Cube Orange+",
    (0x26AC, 0x0034): "Cube Yellow",
    (0x3162, 0x004B): "Matek F405-Wing",
    (0x3162, 0x004C): "Matek F765-Wing",
    (0x3162, 0x004D): "Matek H743-Wing",
}


def resolve_board_from_text(raw_text):
    if not raw_text:
        return None
    s = str(raw_text).strip()
    if re.search(r'\bSITL\b', s, re.IGNORECASE):
        return 'SITL'
    # Check for known hardware vendor/board names
    patterns = [
        (r'\b(SpeedyBee\s*F[0-9]{3}[A-Za-z0-9_\-]*)\b', 'SpeedyBee'),
        (r'\b(Matek\s*[A-Za-z0-9_\-]+)\b', 'Matek'),
        (r'\b(Cube\s*[A-Za-z0-9_\-+]+)\b', 'Cube'),
        (r'\b(Pixhawk\s*[0-9A-Za-z_\-]+)\b', 'Pixhawk'),
        (r'\b(Kakute\s*[A-Za-z0-9_\-]+)\b', 'Kakute'),
        (r'\b(Holybro\s*[A-Za-z0-9_\-]+)\b', 'Holybro'),
        (r'\b(CUAV\s*[A-Za-z0-9_\-]+)\b', 'CUAV'),
        (r'\b(Omnibus\s*[A-Za-z0-9_\-]+)\b', 'Omnibus'),
        (r'\b(Mamba\s*[A-Za-z0-9_\-]+)\b', 'Mamba'),
        (r'\b(AtomRC\s*[A-Za-z0-9_\-]+)\b', 'AtomRC'),
        (r'\b(Foxeer\s*[A-Za-z0-9_\-]+)\b', 'Foxeer'),
        (r'\b(Flywoo\s*[A-Za-z0-9_\-]+)\b', 'Flywoo'),
        (r'\b(Diatone\s*[A-Za-z0-9_\-]+)\b', 'Diatone'),
        (r'\b(JHEMCU\s*[A-Za-z0-9_\-]+)\b', 'JHEMCU'),
        (r'\b(Skystars\s*[A-Za-z0-9_\-]+)\b', 'Skystars'),
        (r'\b(Radiolink\s*[A-Za-z0-9_\-]+)\b', 'Radiolink'),
        (r'\b(SIYI\s*[A-Za-z0-9_\-]+)\b', 'SIYI'),
        (r'\b(Durandal\s*[A-Za-z0-9_\-]+)\b', 'Durandal'),
    ]
    for pattern, brand in patterns:
        m = re.search(pattern, s, re.IGNORECASE)
        if m:
            return format_fc_board_name(m.group(1))
    return None


def resolve_board_name(board_version, vendor_id=0, product_id=0, is_network_sitl=False):
    # Check direct USB VID:PID
    if (vendor_id, product_id) in USB_VID_PID_MAP:
        return USB_VID_PID_MAP[(vendor_id, product_id)]

    if board_version:
        # Direct match on integer board ID (e.g. from BRD_TYPE or AP_BOARD_ID)
        if board_version in BOARD_ID_MAP:
            return format_fc_board_name(BOARD_ID_MAP[board_version])
        # Check upper 16 bits (standard ChibiOS board ID format: board_id << 16)
        bid_high = (board_version >> 16) & 0xFFFF
        if bid_high in BOARD_ID_MAP:
            return format_fc_board_name(BOARD_ID_MAP[bid_high])
        # Check lower 16 bits
        bid_low = board_version & 0xFFFF
        if bid_low in BOARD_ID_MAP:
            return format_fc_board_name(BOARD_ID_MAP[bid_low])
        # Check middle 16 bits (board_version >> 8)
        bid_mid = (board_version >> 8) & 0xFFFF
        if bid_mid in BOARD_ID_MAP:
            return format_fc_board_name(BOARD_ID_MAP[bid_mid])
        # Check byte 2 (board_version >> 8 & 0xFF)
        bid_b2 = (board_version >> 8) & 0xFF
        if bid_b2 in BOARD_ID_MAP:
            return format_fc_board_name(BOARD_ID_MAP[bid_b2])
        # Check byte 3 (board_version >> 16 & 0xFF)
        bid_b3 = (board_version >> 16) & 0xFF
        if bid_b3 in BOARD_ID_MAP:
            return format_fc_board_name(BOARD_ID_MAP[bid_b3])

    # Only return SITL if explicitly verified as a local SITL TCP connection
    if is_network_sitl and vendor_id == 0 and product_id == 0 and board_version == 0:
        return 'SITL'

    if not board_version:
        return 'SITL' if is_network_sitl else None

    return f"FC Board #{bid_high or bid_low}"


def uid_to_usb_serial(uid_text):
    """
    Convert ArduPilot 96-bit STM32 Unique Device ID words (e.g. '003C0028 33334710 32393731')
    to the USB Serial Number representation ('28003C001047333331373932') reported by Windows
    and standard USB device descriptors.
    """
    if not uid_text:
        return None
    words = str(uid_text).strip().split()
    if len(words) != 3:
        return None
    res = ''
    try:
        for w in words:
            if len(w) == 8:
                b = bytes.fromhex(w)
                res += b[::-1].hex().upper()
        return res if len(res) == 24 else None
    except Exception:
        return None


def get_connected_ardupilot_usb_devices():
    """
    Scan local USB bus for connected ArduPilot / ChibiOS flight controllers.
    Returns a list of dictionaries containing device name (e.g. 'COM6'), serial number,
    hardware ID, description, and manufacturer.
    """
    devices = []
    try:
        import serial.tools.list_ports
        for p in serial.tools.list_ports.comports():
            hwid = str(getattr(p, 'hwid', '') or '')
            desc = str(getattr(p, 'description', '') or '')
            mfr = str(getattr(p, 'manufacturer', '') or '')
            prod = str(getattr(p, 'product', '') or '')
            dev = str(getattr(p, 'device', '') or '')
            if (
                '1209:5741' in hwid
                or '26AC:' in hwid
                or '3162:' in hwid
                or 'ArduPilot' in desc
                or 'ArduPilot' in mfr
                or 'Cube' in desc
            ):
                m_ser = re.search(r'SER=([A-Fa-f0-9]+)', hwid)
                ser = m_ser.group(1).upper() if m_ser else (getattr(p, 'serial_number', '') or '').upper()
                devices.append({
                    'device': dev,
                    'serial_number': ser,
                    'hwid': hwid,
                    'description': desc,
                    'manufacturer': mfr,
                    'product': prod
                })
    except Exception:
        pass
    return devices


def find_board_from_recent_tlogs(connected_usb_serials=None):
    """
    Search recent telemetry logs (.tlog) recorded by MAVProxy or Mission Planner on the host machine.
    Immediately extracts the flight controller board name and boot banner without requiring a reboot.
    """
    candidate_dirs = [
        os.getcwd(),
        os.path.expanduser('~'),
        r'C:\Users\KARSHAK_Tamal\Desktop\Git\ArdupilotSITL',
        r'C:\Users\KARSHAK_Tamal\.gemini\antigravity-ide\scratch\ArdupilotLogViewer',
        os.path.join(os.path.expanduser('~'), 'Documents', 'Mission Planner', 'logs'),
    ]
    seen_files = set()
    candidate_files = []
    now = time.time()

    for d in candidate_dirs:
        if not os.path.exists(d):
            continue
        patterns = ['mav.tlog', '*.tlog']
        if 'Mission Planner' in d:
            patterns = ['**/*.tlog', '*.tlog']
        for pat in patterns:
            try:
                for f in glob.glob(os.path.join(d, pat), recursive=True):
                    f_abs = os.path.abspath(f)
                    if f_abs in seen_files:
                        continue
                    seen_files.add(f_abs)
                    try:
                        mtime = os.path.getmtime(f_abs)
                        if now - mtime < 48 * 3600:
                            candidate_files.append((mtime, f_abs))
                    except Exception:
                        pass
            except Exception:
                pass

    candidate_files.sort(key=lambda x: x[0], reverse=True)

    for mtime, fpath in candidate_files[:6]:
        mlog = None
        try:
            from pymavlink import mavutil
            mlog = mavutil.mavlink_connection(fpath)
            for _ in range(400):
                msg = mlog.recv_match(type=['STATUSTEXT', 'AUTOPILOT_VERSION'], blocking=False)
                if msg is None:
                    break
                if msg.get_type() == 'STATUSTEXT':
                    text = getattr(msg, 'text', '')
                    board = resolve_board_from_text(text)
                    if board and board.upper() != 'SITL':
                        m_uid = re.search(r'([0-9A-Fa-f]{8}\s+[0-9A-Fa-f]{8}\s+[0-9A-Fa-f]{8})', text)
                        if m_uid:
                            uid_ser = uid_to_usb_serial(m_uid.group(1))
                            if connected_usb_serials and uid_ser in connected_usb_serials:
                                return board, f'matched USB serial {uid_ser}'
                        return board, f'matched boot banner in {os.path.basename(fpath)}'
                elif msg.get_type() == 'AUTOPILOT_VERSION':
                    bv = getattr(msg, 'board_version', 0)
                    resolved = resolve_board_name(bv)
                    if resolved and resolved.upper() != 'SITL':
                        return resolved, f'AUTOPILOT_VERSION {bv}'
        except Exception:
            pass
        finally:
            if mlog is not None:
                try:
                    mlog.close()
                except Exception:
                    pass
    return None, None


def resolve_fc_hardware_environment(is_network_sitl=False):
    """
    Resolve flight controller hardware identity using all available local telemetry logs,
    connected USB hardware serials, and system descriptors.
    """
    if is_network_sitl:
        return 'SITL', 'local SITL TCP link'

    usb_devs = get_connected_ardupilot_usb_devices()

    # 1. Check if any connected USB COM port directly identifies the board
    for d in usb_devs:
        for text_val in [d.get('description'), d.get('product'), d.get('hwid')]:
            found = resolve_board_from_text(text_val)
            if found and found.upper() != 'SITL':
                return found, f"USB descriptor on {d.get('device')}"

    # 2. Extract hardware identity from recent telemetry logs correlating with USB serials
    usb_sers = [d['serial_number'] for d in usb_devs if d.get('serial_number')]
    board_log, reason = find_board_from_recent_tlogs(usb_sers)
    if board_log:
        return board_log, reason

    # 3. If a physical ArduPilot USB device is connected but specific board banner is absent
    if usb_devs:
        return 'ArduPilot Hardware FC', f"physical device on {usb_devs[0]['device']}"

    return None, 'unresolved'
