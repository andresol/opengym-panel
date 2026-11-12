#include "gym_panel.h"
#include <cmath>
namespace esphome { namespace gym_panel {
namespace { struct Receive {std::string body;bool overflow=false;};
std::string txt(JsonVariantConst v,size_t max){const char*s=v.as<const char*>();if(!s)return {};std::string out(s);if(out.size()>max)return {};return out;}
void label(lv_obj_t *obj,const std::string&s){if(obj)lv_label_set_text(obj,s.c_str());}
}
void GymPanel::setup(){
 mutex_=xSemaphoreCreateMutex();if(!mutex_){mark_failed();return;}
 if(xTaskCreate(worker_entry,"gym_fetch",8192,this,1,&task_)!=pdPASS)mark_failed();
}
esp_err_t GymPanel::http_event(esp_http_client_event_t *e){
 auto*r=static_cast<Receive*>(e->user_data);
 if(e->event_id==HTTP_EVENT_ON_DATA&&e->data_len>0){if(r->body.size()+e->data_len>48000){r->overflow=true;return ESP_FAIL;}r->body.append(static_cast<char*>(e->data),e->data_len);}return ESP_OK;
}
void GymPanel::worker(){
 uint32_t seen=0,last=0;
 while(true){
  const auto gen=generation_.load();const uint32_t now=millis();
  if(wifi::global_wifi_component->is_connected()&&(gen!=seen||now-last>=30000)){
   const int day=wanted_day_.load();std::string url=url_+(day<0?"":"?day="+std::to_string(day));
   Receive receive;receive.body.reserve(8192);esp_http_client_config_t cfg={};cfg.url=url.c_str();cfg.timeout_ms=4000;cfg.disable_auto_redirect=true;cfg.event_handler=http_event;cfg.user_data=&receive;cfg.buffer_size=2048;
   auto client=esp_http_client_init(&cfg);bool ok=false;
   if(client){std::string auth="Bearer "+token_;esp_http_client_set_header(client,"Authorization",auth.c_str());esp_http_client_set_header(client,"Accept","application/json");auto err=esp_http_client_perform(client);ok=err==ESP_OK&&esp_http_client_get_status_code(client)==200&&!receive.overflow;esp_http_client_cleanup(client);}
   if(xSemaphoreTake(mutex_,pdMS_TO_TICKS(500))==pdTRUE){pending_=std::move(receive.body);result_ok_=ok;result_generation_=gen;result_ready_=true;xSemaphoreGive(mutex_);}
   seen=gen;last=millis();
  }
  vTaskDelay(pdMS_TO_TICKS(100));
 }
}
void GymPanel::bind(lv_obj_t*a,lv_obj_t*b,lv_obj_t*c,lv_obj_t*d,lv_obj_t*e,lv_obj_t*f,lv_obj_t*g,lv_obj_t*h,lv_obj_t*i,lv_obj_t*j,lv_obj_t*k,std::array<lv_obj_t*,7> days,std::array<lv_obj_t*,6> controls){
 labels_={a,b,c,d,e,f,g,h,i,j,k};days_=days;controls_=controls;bound_=true;render();
}
bool GymPanel::accept(const std::string &body){
 std::vector<Entry> next;std::string title,date,revision;int day=-1;std::array<bool,7> week{};
 const bool ok=json::parse_json(body,[&](JsonObject root){
  if(root["schema"].as<int>()!=1||!root["entries"].is<JsonArray>()||!root["week"].is<JsonArray>())return false;
  const auto rows=root["entries"].as<JsonArray>();if(rows.size()>40||root["week"].as<JsonArray>().size()!=7)return false;
  title=txt(root["title"],640);date=txt(root["date"],10);revision=txt(root["revision"],32);day=root["day"].as<int>();
  if(title.empty()||date.size()!=10||revision.empty()||day<0||day>6)return false;
  for(int n=0;n<7;n++)week[n]=root["week"][n].as<bool>();
  for(JsonObject r:rows){Entry e;e.name=txt(r["name"],480);e.target=txt(r["target"],160);e.load=txt(r["load"],160);e.detail=txt(r["detail"],480);e.note=txt(r["note"],1000);const float rest=r["restSeconds"].as<float>();if(e.name.empty()||!std::isfinite(rest)||rest<0||rest>3600)return false;e.rest=rest;next.push_back(e);}
  return true;
 });
 if(!ok)return false;
 bool changed=!valid_||revision!=revision_||date!=date_;entries_=std::move(next);title_=title;date_=date;revision_=revision;day_=day;week_=week;valid_=true;last_success_=millis();
 if(changed||selected_>=entries_.size()){selected_=0;timer_reset();}render();return true;
}
void GymPanel::unavailable(){valid_=false;entries_.clear();title_.clear();timer_.reset(0);render();}
void GymPanel::loop(){
 if(!bound_)return;
 if(mutex_&&xSemaphoreTake(mutex_,0)==pdTRUE){
  if(result_ready_){std::string body=std::move(pending_);const bool ok=result_ok_;const auto gen=result_generation_;result_ready_=false;xSemaphoreGive(mutex_);if(gen==generation_.load()){if(!ok||!accept(body))unavailable();}}
  else xSemaphoreGive(mutex_);
 }
 if(valid_&&(!wifi::global_wifi_component->is_connected()||millis()-last_success_>70000))unavailable();
 if(millis()-last_render_>=200){timer_.tick(millis());render();last_render_=millis();}
}
void GymPanel::select_day(int day){if(day<0||day>6)return;wanted_day_=day;++generation_;unavailable();label(labels_[8],"Henter økt …");}
void GymPanel::navigate(int delta){if(!valid_||entries_.empty())return;int n=static_cast<int>(selected_)+delta;if(n<0||n>=static_cast<int>(entries_.size()))return;selected_=n;timer_reset();render();}
void GymPanel::timer_toggle(){if(valid_&&!entries_.empty()){timer_.toggle(millis(),entries_[selected_].rest);render();}}
void GymPanel::timer_adjust(int delta){if(valid_&&!entries_.empty()){timer_.adjust(delta,millis());render();}}
void GymPanel::timer_reset(){timer_.reset(valid_&&!entries_.empty()?entries_[selected_].rest:0);}
void GymPanel::render(){
 if(!bound_)return;
 const Entry*e=valid_&&!entries_.empty()?&entries_[selected_]:nullptr;
 label(labels_[0],valid_?title_:"OpenGym utilgjengelig");label(labels_[1],e?"ØVELSE "+std::to_string(selected_+1)+" / "+std::to_string(entries_.size()):"");
 label(labels_[2],e?e->name:valid_?"Ingen planlagt styrkeøkt":"Kan ikke hente økten");label(labels_[3],e?e->target:"");label(labels_[4],e?e->load:"");label(labels_[5],e?e->detail:"");label(labels_[6],e?e->note:"");
 auto r=timer_.remaining(millis());char buf[16];snprintf(buf,sizeof(buf),"%02u:%02u",unsigned(r/60),unsigned(r%60));label(labels_[7],buf);
 label(labels_[8],valid_?"Oppdatert · plan for neste øktstart":"Frakoblet · ingen ferske treningsdata");label(labels_[9],valid_?date_:"");
 label(labels_[10],timer_.running?"Stopp pause":r==0?"Start på nytt":"Start pause");
 for(int n=0;n<7;n++){bool sel=valid_&&day_==n;lv_obj_set_style_bg_color(days_[n],lv_color_hex(sel?0x78e0b0:0x24344b),LV_PART_MAIN);lv_obj_set_style_text_color(days_[n],lv_color_hex(sel?0x10241d:0xf1f5f9),LV_PART_MAIN);}
 for(int n=0;n<6;n++){bool disable=!e||(n==0&&selected_==0)||(n==1&&selected_+1>=entries_.size());if(disable)lv_obj_add_state(controls_[n],LV_STATE_DISABLED);else lv_obj_remove_state(controls_[n],LV_STATE_DISABLED);}
}
}}
