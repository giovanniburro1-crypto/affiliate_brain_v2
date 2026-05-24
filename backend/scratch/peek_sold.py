import pandas as pd
df = pd.read_excel("/Users/andreylp/affiliate_brain/SOLD.xlsx")
df = df.dropna(how='all')
print(df.head())
print("Columns:", len(df.columns))
