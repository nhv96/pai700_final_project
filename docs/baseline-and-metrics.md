# 1. The data

Each building has one row per hour in the gold layer. The value HtTot is the heat used in that hour, in Wh. Because each row covers one hour, 1,000 Wh is 1 kWh. Some hours are missing, because bad hours were dropped in the ETL.

# 2. Cutting time into blocks

- Final test block: 2022-03-01 to 2023-10-22. We have not used it yet.
- 10 validation blocks ("folds") of 6 months each: fold 1 is 2017-03 to 2017-09, and fold 10 is 2021-09 to 2022-03.
- For fold k, the training data is everything before that fold's start. The validation data is the 6-month block itself.
- Training grows with each fold (expanding window). Training never includes anything from the future of its validation block.
- The dates are the same for all three buildings.

# 3. What one sample ("window") is

For one forecast:
- Origin t: the last hour we know.
- Target: the hour we want to predict, t + h, where h is the horizon (1, 6 or 24 hours).
- History: the 168 hours up to and including t.

A window is valid only if every hour from t−167 to t+h exists in gold. Hours with gaps are never used.

A window belongs to a split by its target hour. A window whose target is in the validation block is a validation window, even if its history reaches back into the training period. That is allowed, because the history is already known at the origin. Training windows must have their target before the validation block starts.

# 4. The baseline forecast: "seasonal naive"

The baseline copies the value from one season earlier. In our case a season is a day or a week:

- Lag 24: the prediction for the target hour is the HtTot of the same hour yesterday, i.e. at t + h − 24.
- Lag 168: the same, but one week earlier, at t + h − 168.

Example: the origin is Tuesday 02:00 and h = 6, so the target is Tuesday 08:00. Lag 24 uses Monday 08:00 and lag 168 uses last Tuesday 08:00. Both hours lie inside the 168-hour history of a valid window, so the baseline always has a value. It uses only past HtTot and no weather and no scaling (Wh straight from gold).

# 5. Choosing between lag 24 and lag 168

This is done for each combination of fold, building and horizon:
1. Take the training windows of that fold.
2. Compute the total absolute error of both lags on them. The lag with the smaller total wins. This is the same as choosing the lower WAPE, because both lags are compared against the same actual values.
3. Use the winning lag to predict the validation windows.

The choice never looks at the validation block, so it is honest. In our first run, lag 24 won everywhere.

(Persistence, which repeats the last value, exists in the code. It is only meaningful for h = 1, and I did not include it in the first run.)

# 6. The metrics

For a group of windows with actual values y and predictions p:
- MAE (kWh): the average of |p − y|, divided by 1000. It answers: "on average, how many kWh am I off per hour?"
- RMSE (kWh): the square root of the average of (p − y)², divided by 1000. It punishes big misses more than MAE does.
- WAPE: the sum of |p − y| divided by the sum of y. For example, 0.235 means the total error is 23.5% of the total heat used. Because it uses sums, an hour with a small actual value doesn't distort it.
- Skill score: 1 − WAPE_model / WAPE_baseline. 0 means no better than the baseline, 0.3 means 30% less error, and 1 means perfect.

# 7. The seasons and the summer rule

Each window gets a season from the month of its target hour: winter is December to February, spring is March to May, summer is June to August, and autumn is September to November.

- WAPE is unstable in summer: when the total heat is close to zero, even small errors give a huge ratio. So for summer we report MAE and RMSE in kWh only, and WAPE and skill are left empty.
- The "all seasons" row still includes summer hours in its sums. In that row summer adds almost nothing to the denominator, so WAPE stays stable.

# 8. How the first reference numbers were produced

I looped over the horizons 1, 6 and 24, over all 10 folds and over all 3 buildings, and collected every validation window. I pooled them, meaning I pooled the raw errors (not an average of the folds' scores) and then computed the metrics per horizon and season. Pooling means large buildings and winter hours count more, because they have more heat and more windows.

In that run, the prediction and the baseline were the same thing, so the table shows the baseline's own error. That is the number a model must beat. For example, WAPE is about 0.235 for every horizon, and winter MAE is about 47 kWh.

# 9. What happens when a model exists

For every validation window you will have y_true, the model's y_pred, and the baseline's y_base (the chosen lag, as above). score_table then gives MAE, RMSE, WAPE and skill per fold, building, horizon and season, next to the baseline's own MAE and WAPE.

Things to keep in mind

- Results are for the future of known buildings: the buildings in validation are the same as in training. It tells you nothing about a completely new building.
- Pooling hides differences: building 8107 has 34,900 windows against 57,091 for 8116, and winter dominates the totals. I'd look at the per-fold and per-building tables as well, not only the pooled one.
- The test block is untouched: all numbers so far are validation numbers. The test block should be used once, at the end.