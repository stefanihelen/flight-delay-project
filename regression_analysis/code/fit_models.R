# Full-cohort association and temporal prediction models. No random downsampling.
args <- commandArgs(trailingOnly = TRUE)
input <- if(length(args)>=1) args[1] else 'work/model_data.csv'
out <- if(length(args)>=2) args[2] else 'outputs/member4_regression'
work <- if(length(args)>=3) args[3] else 'work'
if(dir.exists('work/r-lib')) .libPaths(c(normalizePath('work/r-lib'), .libPaths()))
suppressPackageStartupMessages({library(data.table); library(fixest); library(jsonlite)})
setDTthreads(2); setFixest_nthreads(2)
dir.create(file.path(out,'tables'), recursive=TRUE, showWarnings=FALSE)
tab <- file.path(out,'tables')
logmsg <- function(...) {cat(format(Sys.time(),'%Y-%m-%d %H:%M:%S'),..., '\n'); flush.console()}
logmsg('READ',input)
d <- fread(input, showProgress=FALSE,colClasses=c(station='character'))
for(v in c('origin','dest','airline','station','route')) set(d,j=v,value=as.factor(d[[v]]))
d[, sin1:=sin(2*pi*date_id/366)]; d[, cos1:=cos(2*pi*date_id/366)]
d[, sin2:=sin(4*pi*date_id/366)]; d[, cos2:=cos(4*pi*date_id/366)]
logmsg('READ_DONE',nrow(d),'rows',format(object.size(d),units='MB'))
weather <- 'i(wind, ref=0) + i(vis, ref=0) + rain + temp10 + temp10sq'
main_rhs <- paste(weather,'+ distance_log | origin + dest + airline + month + weekday + hour')
pred_rhs <- paste(weather,'+ distance_log + sin1 + cos1 + sin2 + cos2 | origin + dest + airline + weekday + hour')
base_rhs <- 'distance_log + sin1 + cos1 + sin2 + cos2 | origin + dest + airline + weekday + hour'
diag_all <- list(); contrasts_all <- list()
fit_one <- function(name, rows, response, rhs, get_contrasts=TRUE){
  gc(); logmsg('FIT_START',name,'eligible',sum(rows))
  f <- as.formula(paste(response,'~',rhs))
  needed <- unique(c(all.vars(f),'origin','date_id'))
  dd <- d[rows,..needed]
  fit_warnings <- character()
  m <- withCallingHandlers(feglm(f,data=dd,family='binomial',vcov=~origin+date_id,
             mem.clean=TRUE,nthreads=2,glm.iter=50,glm.tol=1e-8,notes=TRUE),
             warning=function(w) fit_warnings <<- c(fit_warnings,conditionMessage(w)))
  if(!isTRUE(m$convStatus)) stop(paste('Model did not converge:',name))
  b <- coef(m); V <- vcov(m)
  used <- obs(m)
  g1 <- uniqueN(dd$origin[used]); g2 <- uniqueN(dd$date_id[used])
  df <- min(g1,g2)-1; crit <- qt(.975,df)
  se <- sqrt(diag(V))
  ct <- data.table(model=name,term=names(b),estimate=as.numeric(b),se=se,
                   lower=as.numeric(b)-crit*se,upper=as.numeric(b)+crit*se,
                   p_value=2*pt(-abs(b/se),df),df=df)
  fwrite(ct,file.path(tab,paste0(name,'_coefficients.csv')))
  meta <- list(model=name,formula=deparse(f),n_eligible=nrow(dd),n_model=nobs(m),
               removed_by_estimator=nrow(dd)-nobs(m),converged=m$convStatus,
               iterations=m$iterations,origins=g1,dates=g2,cluster_df=df,
               mean_outcome=mean(dd[[response]][used]),collin_removed=m$collin.var,warnings=fit_warnings,
               fixed_effects_removed=lapply(m$fixef_removed,length),
               log_likelihood=as.numeric(logLik(m)))
  diag_all[[name]] <<- meta
  write_json(diag_all,file.path(tab,'model_diagnostics.json'),pretty=TRUE,auto_unbox=TRUE,null='null')
  if(get_contrasts){
    defs <- list(wind_5_10=c('wind::1'=1),wind_10_20=c('wind::2'=1),wind_20_plus=c('wind::3'=1),
                 visibility_5_10km=c('vis::1'=1),visibility_1_5km=c('vis::2'=1),visibility_under_1km=c('vis::3'=1),
                 rain_vs_dry=c(rain=1),temperature_5_to_15=c(temp10=1,temp10sq=-1),temperature_15_to_25=c(temp10=1,temp10sq=1))
    ctab <- rbindlist(lapply(names(defs),function(nm){
      a <- setNames(rep(0,length(b)),names(b)); spec <- defs[[nm]]
      if(!all(names(spec)%in%names(b))) return(NULL)
      a[names(spec)] <- spec; est <- sum(a*b); ses <- sqrt(as.numeric(t(a)%*%V%*%a))
      data.table(model=name,contrast=nm,log_or=est,se=ses,odds_ratio=exp(est),
                 lower=exp(est-crit*ses),upper=exp(est+crit*ses),p_value=2*pt(-abs(est/ses),df),n=nobs(m))
    }))
    contrasts_all[[name]] <<- ctab
    fwrite(rbindlist(contrasts_all),file.path(tab,'weather_contrasts.csv'))
    if(name=='main'){
      fwrite(as.data.table(V,keep.rownames='term'),file.path(tab,'main_covariance.csv'))
      grid <- seq(-10,40,by=1); a <- (grid-15)/10
      est <- b['temp10']*a+b['temp10sq']*a*a
      ses <- sqrt(a*a*V['temp10','temp10']+a^4*V['temp10sq','temp10sq']+2*a^3*V['temp10','temp10sq'])
      fwrite(data.table(temp_c=grid,odds_ratio_vs15=exp(est),lower=exp(est-crit*ses),upper=exp(est+crit*ses)),file.path(tab,'temperature_curve.csv'))
      logmsg('MAIN_WEATHER',paste(ctab$contrast,round(ctab$odds_ratio,3),collapse='; '))
    }
  }
  logmsg('FIT_DONE',name,'n',nobs(m),'iterations',m$iterations)
  rm(dd);gc(); m
}
main_rows <- d$y_delay>=0
m <- fit_one('main',main_rows,'y_delay',main_rhs);rm(m);gc()
m <- fit_one('window60',main_rows & d$within60==1,'y_delay',main_rhs);rm(m);gc()
m <- fit_one('strict_quality',main_rows & d$strict_q==1,'y_delay',main_rhs);rm(m);gc()
m <- fit_one('route_fe',main_rows,'y_delay',paste(weather,'| route + airline + month + weekday + hour'));rm(m);gc()
m <- fit_one('disruption',d$y_disrupt>=0,'y_disrupt',main_rhs);rm(m);gc()
# Seasonal Fourier terms permit prediction for months unseen in training.
train <- main_rows & d$month<=8
hold <- d[main_rows & month>=9,.(date_id,month,y=y_delay)]
for(name in c('baseline','weather')){
  rhs <- if(name=='baseline') base_rhs else pred_rhs
  m <- fit_one(paste0('predict_',name),train,'y_delay',rhs,FALSE)
  logmsg('PREDICT_START',name)
  p <- predict(m,newdata=d[main_rows & month>=9],type='response')
  hold[,(paste0('p_',name)):=p]
  rm(m,p);gc()
}
fwrite(hold,file.path(work,'holdout_predictions.csv'))
fwrite(d[,.(n=.N,delayed=sum(y_delay==1),valid_arrivals=sum(y_delay>=0),disruptions=sum(y_disrupt==1)),by=month],file.path(tab,'model_cohort_monthly.csv'))
writeLines(capture.output(sessionInfo()),file.path(out,'R_session_info.txt'))
logmsg('ALL_MODELS_DONE')
