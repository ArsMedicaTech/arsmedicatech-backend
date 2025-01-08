""""""


sql_query = """
CREATE TABLE `formAR` (
  `ID` int(10) NOT NULL AUTO_INCREMENT,
  `demographic_no` int(10) NOT NULL DEFAULT '0',
  `provider_no` varchar(6) DEFAULT NULL,
  `formCreated` date DEFAULT NULL,
  `formEdited` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `c_lastVisited` char(3) DEFAULT NULL,
  `c_pName` varchar(60) DEFAULT NULL,
  `c_address` varchar(80) DEFAULT NULL,
  `pg1_dateOfBirth` date DEFAULT NULL,
  `pg1_age` char(2) DEFAULT NULL,
  `pg1_msSingle` tinyint(1) DEFAULT NULL,
  `pg1_msCommonLaw` tinyint(1) DEFAULT NULL,
  `pg1_msMarried` tinyint(1) DEFAULT NULL,
  `pg1_eduLevel` varchar(25) DEFAULT NULL,
  `pg2_date1` date DEFAULT NULL,
  `pg2_gest1` varchar(6) DEFAULT NULL,
  `pg2_ht1` varchar(6) DEFAULT NULL,
  `pg2_wt1` varchar(6) DEFAULT NULL,
  `pg2_presn1` varchar(6) DEFAULT NULL,
  `pg3_presn34` varchar(6) DEFAULT NULL,
  `pg3_FHR34` varchar(6) DEFAULT NULL,
  `pg3_urinePr34` char(3) DEFAULT NULL,
  `pg3_urineGl34` char(3) DEFAULT NULL,
  `pg3_BP34` varchar(8) DEFAULT NULL,
  `pg3_comments34` text DEFAULT NULL,
  `pg3_cig34` char(3) DEFAULT NULL,
  `ar2_obstetrician` tinyint(1) DEFAULT NULL,
  `ar2_pediatrician` tinyint(1) DEFAULT NULL,
  `ar2_anesthesiologist` tinyint(1) DEFAULT NULL,
  `ar2_socialWorker` tinyint(1) DEFAULT NULL,
  `ar2_dietician` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`ID`)
) ENGINE=InnoDB
  ROW_FORMAT=DYNAMIC;
"""


def calculate_row_size(sql_string: str):
    row_size = 0
    for line in sql_string.split('\n'):
        print(line)
        line = line.lstrip().rstrip()
        if line.startswith('CREATE TABLE'):
            print("CONTINUING:", line)
            continue
        elif line.startswith('PRIMARY KEY'):
            print("BREAKING:", line)
            break
        elif line == '':
            print("CONTINUING:", line)
            continue
        x = line.split(' ')
        try:
            field_type = x[1].lstrip().rstrip()
        except:
            print("Error:", line)
            continue

        if field_type.startswith('varchar'):
            row_size += int(field_type.split('(')[1].split(')')[0]) * 4
        elif field_type.startswith('char'):
            row_size += int(field_type.split('(')[1].split(')')[0])
        elif field_type.startswith('int'):
            row_size += 4
        elif field_type.startswith('bigint'):
            row_size += 8
        elif field_type.startswith('tinyint'):
            row_size += 1
        elif field_type.startswith('date'):
            row_size += 3
        elif field_type.startswith('timestamp'):
            row_size += 4
        elif field_type.startswith('text'):
            row_size += 20
        else:
            print("Unknown field type:", field_type)
            print(line)
            if '`ID` INT NOT NULL' in line:
                row_size += 4
            else:
                raise Exception("Unknown field type")
    return row_size


print(calculate_row_size(sql_query))  # 202

start_line = 521
end_line = 694

file_path = 'emr/oscar/migrations/initcaisi.sql'

with open(file_path, 'r') as f:
    sql_lines = f.readlines()

    s = ""

    for i, line in enumerate(sql_lines):
        if i == start_line:
            s += line
        elif i > start_line and i < end_line:
            s += line
        elif i == end_line:
            s += line
            break


print(calculate_row_size(s))  # 202
