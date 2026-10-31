import pandas as pd
from pathlib import Path

path = Path(r'C:/Users/Paramasivam/AppData/Local/Packages/5319275A.51895FA4EA97F_cv1g1gvanyjgm/LocalState/sessions/6E404AAF097E768D83179E3117EE6DB0F1804691/transfers/2026-15/indian_corrected_uh_dataset.xlsx')
print('path exists', path.exists())
print('path', path)
xl = pd.ExcelFile(path)
print('sheets', xl.sheet_names)
for sheet in xl.sheet_names:
    df = pd.read_excel(path, sheet_name=sheet)
    print('sheet', sheet, 'shape', df.shape)
    print('columns', df.columns.tolist())
    print(df.head(2).to_dict(orient='records'))
    break
