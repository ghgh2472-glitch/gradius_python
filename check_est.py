import data_loader

d = data_loader.load_all_data()
est = d.get('estimate')
print('estimate rows:', 0 if est is None else len(est))
print('estimate cols:', [] if est is None else list(est.columns))
print('sample rows (up to 5):')
if est is not None and len(est) > 0:
    print(est.head(5).to_string(index=False))
else:
    print('<no rows>')
