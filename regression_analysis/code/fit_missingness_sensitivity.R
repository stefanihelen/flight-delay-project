# Compare the SAME no-precipitation specification on common and expanded cohorts.
args <- commandArgs(trailingOnly=TRUE)
work <- if(length(args)>=1) args[1] else 'work'
out <- if(length(args)>=2) args[2] else 'outputs/member4_regression'
if(dir.exists(file.path(work,'r-lib'))) .libPaths(c(normalizePath(file.path(work,'r-lib')),.libPaths()))
suppressPackageStartupMessages({library(data.table);library(fixest);library(jsonlite)})
setDTthreads(2);setFixest_nthreads(2)
tab <- file.path(out,'tables'); meta <- list(); contrasts <- list()
for(name in c('no_precip_common','no_precip_expanded')){
  gc(); cat(format(Sys.time()),'START',name,'\n');flush.console()
  filename <- if(name=='no_precip_common') 'model_data.csv' else 'model_data_no_precip.csv'
  d <- fread(file.path(work,filename),select=c('y_delay','wind','vis','temp10','temp10sq','distance_log','origin','dest','airline','month','weekday','hour','date_id'))
  d <- d[y_delay>=0]
  for(v in c('origin','dest','airline')) set(d,j=v,value=as.factor(d[[v]]))
  warn <- character()
  m <- withCallingHandlers(feglm(y_delay~i(wind,ref=0)+i(vis,ref=0)+temp10+temp10sq+distance_log|
                origin+dest+airline+month+weekday+hour,data=d,family='binomial',vcov=~origin+date_id,
                mem.clean=TRUE,nthreads=2,glm.iter=50,glm.tol=1e-8),
                warning=function(w) warn<<-c(warn,conditionMessage(w)))
  stopifnot(isTRUE(m$convStatus))
  b<-coef(m);V<-vcov(m);used<-obs(m)
  g1<-uniqueN(d$origin[used]);g2<-uniqueN(d$date_id[used]);df<-min(g1,g2)-1;crit<-qt(.975,df)
  defs<-list(wind_5_10=c('wind::1'=1),wind_10_20=c('wind::2'=1),wind_20_plus=c('wind::3'=1),
             visibility_5_10km=c('vis::1'=1),visibility_1_5km=c('vis::2'=1),visibility_under_1km=c('vis::3'=1),
             temperature_5_to_15=c(temp10=1,temp10sq=-1),temperature_15_to_25=c(temp10=1,temp10sq=1))
  contrasts[[name]]<-rbindlist(lapply(names(defs),function(nm){
    a<-setNames(rep(0,length(b)),names(b));a[names(defs[[nm]])]<-defs[[nm]]
    est<-sum(a*b);se<-sqrt(as.numeric(t(a)%*%V%*%a))
    data.table(model=name,contrast=nm,log_or=est,se=se,odds_ratio=exp(est),
               lower=exp(est-crit*se),upper=exp(est+crit*se),p_value=2*pt(-abs(est/se),df),n=nobs(m))
  }))
  se<-sqrt(diag(V))
  fwrite(data.table(model=name,term=names(b),estimate=as.numeric(b),se=se,lower=as.numeric(b)-crit*se,upper=as.numeric(b)+crit*se),file.path(tab,paste0(name,'_coefficients.csv')))
  meta[[name]]<-list(n_eligible=nrow(d),n_model=nobs(m),removed_by_estimator=nrow(d)-nobs(m),converged=m$convStatus,
                     iterations=m$iterations,origins=g1,dates=g2,cluster_df=df,mean_outcome=mean(d$y_delay[used]),warnings=warn,
                     formula='delay ~ wind categories + visibility categories + temperature + temperature squared + log distance | origin + destination + airline + month + weekday + hour')
  fwrite(rbindlist(contrasts),file.path(tab,'missingness_contrasts.csv'))
  write_json(meta,file.path(tab,'missingness_models.json'),pretty=TRUE,auto_unbox=TRUE,digits=12)
  cat(format(Sys.time()),'DONE',name,'n',nobs(m),'\n');flush.console();rm(m,d);gc()
}
